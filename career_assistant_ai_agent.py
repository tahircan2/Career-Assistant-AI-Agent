from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
import json
import os
import requests
from pypdf import PdfReader
import gradio as gr

load_dotenv(override=True)

openai = OpenAI()


# ── Pushover setup ──────────────────────────────────────────────────────────────
pushover_user  = os.getenv("PUSHOVER_USER")
pushover_token = os.getenv("PUSHOVER_TOKEN")
pushover_url   = "https://api.pushover.net/1/messages.json"

if pushover_user:
    print(f"Pushover user found and starts with {pushover_user[0]}")
else:
    print("Pushover user not found")

if pushover_token:
    print(f"Pushover token found and starts with {pushover_token[0]}")
else:
    print("Pushover token not found")


def push(message):
    print(f"Push: {message}")
    payload = {"user": pushover_user, "token": pushover_token, "message": message}
    requests.post(pushover_url, data=payload)


# ── Tool functions ──────────────────────────────────────────────────────────────
def record_user_details(email, name="Name not provided", notes="not provided"):
    push(f"Recording interest from {name} with email {email} and notes {notes}")
    return {"recorded": "ok"}

def record_unknown_question(question):
    push(f"Unknown question recorded — needs human review: {question}")
    return {"recorded": "ok"}


# ── Tool schemas ────────────────────────────────────────────────────────────────
record_user_details_json = {
    "name": "record_user_details",
    "description": "Use this tool to record that a user is interested in being in touch and provided an email address",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "The email address of this user"},
            "name":  {"type": "string", "description": "The user's name, if they provided it"},
            "notes": {"type": "string", "description": "Any additional information about the conversation"}
        },
        "required": ["email"],
        "additionalProperties": False
    }
}

record_unknown_question_json = {
    "name": "record_unknown_question",
    "description": "Always use this tool to record any question that couldn't be answered as you didn't know the answer",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "The question that couldn't be answered"}
        },
        "required": ["question"],
        "additionalProperties": False
    }
}

tools = [
    {"type": "function", "function": record_user_details_json},
    {"type": "function", "function": record_unknown_question_json}
]


# ── Tool call handler ───────────────────────────────────────────────────────────
def handle_tool_calls(tool_calls):
    results = []
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        print(f"Tool called: {tool_name}", flush=True)
        tool = globals().get(tool_name)
        result = tool(**arguments) if tool else {}
        results.append({
            "role": "tool",
            "content": json.dumps(result),
            "tool_call_id": tool_call.id
        })
    return results


# ── CV / profile context ────────────────────────────────────────────────────────
reader  = PdfReader("me/linkedin.pdf")
linkedin = ""
for page in reader.pages:
    text = page.extract_text()
    if text:
        linkedin += text

with open("me/summary.txt", "r", encoding="utf-8") as f:
    summary = f.read()

name = "Tahircan Saçlı"


# ── Primary agent system prompt ─────────────────────────────────────────────────
system_prompt = (
    f"You are acting as {name}. You are answering questions on {name}'s website, "
    f"particularly questions related to {name}'s career, background, skills and experience. "
    f"Your responsibility is to represent {name} for interactions on the website as faithfully as possible. "
    f"You are given a summary of {name}'s background and LinkedIn profile which you can use to answer questions. "
    "Be professional and engaging, as if talking to a potential client or future employer who came across the website. "
    "If you don't know the answer to any question, use your record_unknown_question tool to record the question that you couldn't answer, even if it's about something trivial or unrelated to career. "
    "If the user is engaging in discussion, try to steer them towards getting in touch via email; ask for their email and record it using your record_user_details tool. "
)
system_prompt += f"\n\n## Summary:\n{summary}\n\n## LinkedIn Profile:\n{linkedin}\n\n"
system_prompt += f"With this context, please chat with the user, always staying in character as {name}."


# ── Evaluator (Gemini as judge) ─────────────────────────────────────────────────
class Evaluation(BaseModel):
    is_acceptable: bool
    feedback: str


evaluator_system_prompt = (
    f"You are an evaluator that decides whether a response to a question is acceptable. "
    f"You are provided with a conversation between a User and an Agent. Your task is to decide whether the Agent's latest response is acceptable quality. "
    f"The Agent is playing the role of {name} and is representing {name} on their website. "
    f"The Agent has been instructed to be professional and engaging, as if talking to a potential client or future employer who came across the website. "
    f"The Agent has been provided with context on {name} in the form of their summary and LinkedIn details. Here's the information:"
)
evaluator_system_prompt += f"\n\n## Summary:\n{summary}\n\n## LinkedIn Profile:\n{linkedin}\n\n"
evaluator_system_prompt += (
    "With this context, please evaluate the latest response. "
    "Check: professional tone, clarity, completeness, safety (no false claims), and relevance. "
    "Reply with whether the response is acceptable and your feedback."
)


def evaluator_user_prompt(reply, message, history):
    prompt  = f"Here's the conversation between the User and the Agent:\n\n{history}\n\n"
    prompt += f"Here's the latest message from the User:\n\n{message}\n\n"
    prompt += f"Here's the latest response from the Agent:\n\n{reply}\n\n"
    prompt += "Please evaluate the response, replying with whether it is acceptable and your feedback."
    return prompt


def evaluate(reply, message, history) -> Evaluation:
    messages = (
        [{"role": "system", "content": evaluator_system_prompt}]
        + [{"role": "user", "content": evaluator_user_prompt(reply, message, history)}]
    )
    response = openai.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=messages,
        response_format=Evaluation
    )
    return response.choices[0].message.parsed


# ── Retry with evaluator feedback ──────────────────────────────────────────────
def rerun(reply, message, history, feedback):
    updated_system = (
        system_prompt
        + "\n\n## Previous answer rejected\n"
        + "You just tried to reply, but the quality control rejected your reply.\n"
        + f"## Your attempted answer:\n{reply}\n\n"
        + f"## Reason for rejection:\n{feedback}\n\n"
    )
    messages = (
        [{"role": "system", "content": updated_system}]
        + history
        + [{"role": "user", "content": message}]
    )
    response = openai.chat.completions.create(model="gpt-4o-mini", messages=messages)
    return response.choices[0].message.content


# ── Main chat function ──────────────────────────────────────────────────────────
def chat(message, history):
    # 1. Notify: new employer message arrived
    push(f"New employer message received: {message[:80]}")

    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]
    done = False

    # 2. Primary agent loop (handles tool calls)
    while not done:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools
        )
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "tool_calls":
            msg        = response.choices[0].message
            tool_calls = msg.tool_calls
            results    = handle_tool_calls(tool_calls)
            messages.append(msg)
            messages.extend(results)
        else:
            done = True

    reply = response.choices[0].message.content

    # 3. Evaluate the response
    evaluation = evaluate(reply, message, history)

    if evaluation.is_acceptable:
        print("✅ Passed evaluation — returning reply")
        push(f"Response approved and sent to employer. Preview: {reply[:80]}")
    else:
        print("❌ Failed evaluation — retrying")
        print(f"Feedback: {evaluation.feedback}")
        reply = rerun(reply, message, history, evaluation.feedback)
        push(f"Response revised and sent. Feedback was: {evaluation.feedback[:80]}")

    return reply


# ── Launch ──────────────────────────────────────────────────────────────────────
gr.ChatInterface(chat, type="messages").launch()
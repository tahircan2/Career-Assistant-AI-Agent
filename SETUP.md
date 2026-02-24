Setup Guide

Hi,

Follow the steps below to run this project on your own computer. Just go step by step and you’ll be fine.

1. Clone the repository

Open Command Prompt and go to the folder where you want the project:

cd C:\Users\YourUsername\Desktop

Clone the repo:

git clone https://github.com/tahircan2/Career-Assistant-AI-Agent.git
cd your-repo-name
2. Create and activate virtual environment

Create the environment:

python -m venv .venv

Activate it:

Windows:

.venv\Scripts\activate

Mac/Linux:

source .venv/bin/activate

3. Install dependencies

pip install -r requirements.txt

4. Create .env file

In the project root folder, create a file named:

.env

Add your API key inside:

OPENAI_API_KEY=your_api_key_here

If needed, you can also add:

GOOGLE_API_KEY=your_google_key
ANTHROPIC_API_KEY=your_anthropic_key

Make sure:

The file name is exactly .env

There is no space around the =

The file is saved in the root project folder

5. Run the project
python career_assistant_ai_agent.py

That’s it.
Your environment should now be ready.
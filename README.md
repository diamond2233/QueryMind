# QueryMind

QueryMind is an AI-powered chatbot project that uses Retrieval-Augmented Generation (RAG) and Google Gemini models to answer questions over structured business data. The project demonstrates how natural language can be used to interact with datasets through semantic retrieval, contextual reasoning, and LLM-generated responses.

## Features

* Natural language querying over business datasets
* Gemini-powered conversational interface
* Retrieval-Augmented Generation (RAG) workflow
* Semantic search over CSV-based data
* RAG evaluation with RAGAS
* Agentic AI workflow experimentation
* Jupyter notebook-based implementation

## Project Structure

* `Gemini Chatbot.ipynb` – Main chatbot implementation using Gemini
* `Gemini Chatbot (including RAGAS).ipynb` – Chatbot with evaluation using RAGAS
* `Agentic Approach.ipynb` – Agentic workflow exploration
* `gemini.ipynb` – Additional Gemini-based experimentation
* `Data_CSV/` – Business datasets used by the project
* `data_dump/` – Additional dataset files

## Tech Stack

* Python
* Jupyter Notebook
* Google Gemini API
* Retrieval-Augmented Generation (RAG)
* RAGAS
* Pandas
* NumPy
* CSV-based data processing

## How It Works

1. The user enters a question in natural language.
2. Relevant data is retrieved from the available CSV files.
3. The retrieved context is passed to Gemini.
4. Gemini generates a response based on both the query and the retrieved data.

## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/diamond2233/QueryMind.git
   cd QueryMind
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Add your Gemini API key in a `.env` file or notebook environment variable.

4. Run the notebooks in Jupyter:

   ```bash
   jupyter notebook
   ```

## Note

This project is best explored through the notebooks included in the repository. Make sure to keep API keys and private files out of version control.

## License

Add a license if you want to make the project easier to reuse.

import os
from groq import Groq

class GroqLLM:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")

        self.client = Groq(api_key=api_key)

    def generate(self, query, context):
        prompt = f"""
You are a helpful assistant.
Answer strictly based on the provided context.
If the answer is not in the context, say "Information not found in the document."

Context:
{context}

Question:
{query}

Answer:
"""

        response = self.client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        return response.choices[0].message.content

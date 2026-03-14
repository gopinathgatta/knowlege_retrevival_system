import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()  # Load .env file


class LLMGenerator:
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY")

        if not self.groq_api_key:
            print("⚠️ GROQ_API_KEY not found. Using Mock Generator.")
            self.client = None
        else:
            self.client = Groq(api_key=self.groq_api_key)
            print("✅ GROQ API Key Set")

    def generate(self, query, context_chunks):
        """
        Generates an answer based on the query and retrieved context.
        """

        if not context_chunks:
            return "No relevant context found."

        # Keep context within Groq's token limits (6000 chars ~ safe limit)
        context_text = "\n\n".join(context_chunks)[:6000]

        system_prompt = """You are an intelligent Knowledge Retrieval Assistant for source code repositories.
Answer questions using the provided context, which contains source code, README files, and documentation.

Guidelines:
- Use code evidence (class names, package structure, method names, imports) to infer and explain architecture.
- For architecture questions, synthesize what the code reveals about design — don't require explicit documentation sentences.
- If the context contains ZERO relevant information, say: "The answer is not available in the provided documents."
- Do NOT invent components that have no evidence in the context.
- Cite specific class names, file names, or patterns found in the context to support your answer.
- If the question has multiple parts, answer each part separately."""

        user_prompt = f"""Context:
{context_text}

Question:
{query}

Answer:"""

        # If GROQ is configured
        if self.client:
            # Try 70b first, fall back to 8b if it fails (rate limit / timeout)
            models_to_try = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

            for model in models_to_try:
                try:
                    response = self.client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.3,
                        timeout=60,
                    )
                    return response.choices[0].message.content

                except Exception as e:
                    print(f"⚠️ Model {model} failed: {e}. Trying next...")
                    continue

            return "❌ All models failed. Please try again in a moment."

        # Fallback mock
        else:
            return f"""[MOCK RESPONSE]

Based on retrieved context:
{context_chunks[0][:200]}...
"""

import anthropic
from config import ANTHROPIC_API_KEY, MODEL

from agent.prompts import build_system_prompt
from agent.tools import TOOLS

client = anthropic.Anthropic()
history = []

def chat(user_message: str) -> str:
    history.append({"role": "user", "content": user_message})

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=1024,
        system=build_system_prompt(),
        tools=TOOLS,
        messages=history,
        max_iterations=5
    )

    final = None
    for message in runner:
        history.append({"role": "assistant", "content": message.content})
        tool_results = runner.generate_tool_call_response()
        if tool_results:
            history.append(tool_results)
        final=message

    return "".join(block.text for block in final.content if block.type == "text")

if __name__ == "__main__":
    print("Empório da Música — digite 'sair' para encerrar\n")
    while True:
        user_input = input("Você: ").strip()
        if user_input.lower() == "sair":
            break
        if user_input:
            print(f"\nEmpório: {chat(user_input)}\n")
import asyncio
import json

from llm.yandex_client import YandexGPTClient
from llm.prompt_builder import PromptBuilder
from llm.rag_module import IngredientRAG
import time


async def main():
    #client = YandexGPTClient()
    #_rag=IngredientRAG()
    #prompt = PromptBuilder.build_prompt(skin_type="Сухая",name="", allergens=["Нет"], preferences=["Нет"],ingredients="Aqua,Lactobionic Acid, Glycerin, Cetyl Alcohol, Parfum, Unicorn Extract",rag=_rag)
    #start = time.time()
    ##response = await client.generate_response(prompt)
    #end = time.time()
    ##print(response)
    #print(prompt)
    #print(end-start)

     with open("data/ingredients.json", 'r', encoding='utf-8') as f:
        data = json.load(f)
        for ingredient in data['ingredients']:
            print(ingredient['name'])
asyncio.run(main())
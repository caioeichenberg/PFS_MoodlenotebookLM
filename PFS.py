import asyncio
from notebooklm import NotebookLMClient, InfographicOrientation, InfographicDetail


async def main():
    async with NotebookLMClient.from_storage() as client:

        # Cria notebook e adiciona uma fonte
        notebook = await client.notebooks.create("Estudo - Resumos Automáticos")
        print(f"Notebook criado: {notebook.id}")

        await client.sources.add_url(
            notebook.id,
            "https://pt.wikipedia.org/wiki/Inteligência_artificial",
            wait=True,  # espera o NotebookLM terminar de indexar a fonte
        )
        print("Fonte adicionada e processada.\n")

        #inicia a geração do PODCAST (áudio)
        print("Iniciando geração do resumo em áudio (podcast)...")
        audio_status = await client.artifacts.generate_audio(
            notebook.id,
            instructions="Resuma os pontos principais do material de forma clara e objetiva.",
        )

        # inicia a geração do INFOGRÁFICO
        print("Iniciando geração do resumo em infográfico...")
        infografico_status = await client.artifacts.generate_infographic(
            notebook.id,
            instructions="Resuma os conceitos-chave do material.",
            orientation=InfographicOrientation.PORTRAIT,
            detail_level=InfographicDetail.STANDARD,  # nome correto do parâmetro: detail_level
        )

        # Esperar as duas gerações terminarem (cada uma pode levar muitos minutos)
        print("\nAguardando a conclusão das gerações (pode levar alguns minutos)...")
        audio_final = await client.artifacts.wait_for_completion(
            notebook.id, audio_status.task_id, timeout=900
        )
        infografico_final = await client.artifacts.wait_for_completion(
            notebook.id, infografico_status.task_id, timeout=900
        )

        # Baixar os arquivos finais para o disco
        if audio_final.is_complete:
            caminho_audio = await client.artifacts.download_audio(
                notebook.id, "resumo_podcast.mp3"
            )
            print(f"Podcast salvo em: {caminho_audio}")
        else:
            print(f"Falha ao gerar o áudio: {audio_final.status}")

        if infografico_final.is_complete:
            caminho_infografico = await client.artifacts.download_infographic(
                notebook.id, "resumo_infografico.png"
            )
            print(f"Infográfico salvo em: {caminho_infografico}")
        else:
            print(f"Falha ao gerar o infográfico: {infografico_final.status}")


if __name__ == "__main__":
    asyncio.run(main())

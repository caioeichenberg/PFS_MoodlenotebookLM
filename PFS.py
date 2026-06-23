import asyncio

from notebooklm import (
    NotebookLMClient,
    InfographicOrientation,
    InfographicDetail,
    AudioFormat,
    VideoFormat,
    SlideDeckFormat,
    QuizQuantity,
    QuizDifficulty,
    ReportFormat,
)

INSTRUCOES_PADRAO = "Resuma os pontos principais do material de forma clara e objetiva."

# Cada entrada descreve um formato de resumo:
# - label: nome exibido no menu
# - filename: nome do arquivo salvo localmente
# - generate: função que dispara a geração (recebe client e notebook_id)
# - download: função que baixa o artefato já concluído
ARTIFACT_SPECS = {
    "1": {
        "label": "Áudio / Podcast",
        "filename": "resumo_podcast.mp3",
        "generate": lambda c, nb: c.artifacts.generate_audio(
            nb,
            instructions=INSTRUCOES_PADRAO,
            language="pt_BR",
            audio_format=AudioFormat.DEEP_DIVE,
        ),
        "download": lambda c, nb, artifact_id, path: c.artifacts.download_audio(
            nb, path, artifact_id
        ),
    },
    "2": {
        "label": "Infográfico",
        "filename": "resumo_infografico.png",
        "generate": lambda c, nb: c.artifacts.generate_infographic(
            nb,
            instructions="Resuma os conceitos-chave do material.",
            language="pt_BR",
            orientation=InfographicOrientation.PORTRAIT,
            detail_level=InfographicDetail.STANDARD,
        ),
        "download": lambda c, nb, artifact_id, path: c.artifacts.download_infographic(
            nb, path, artifact_id
        ),
    },
    "3": {
        "label": "Vídeo",
        "filename": "resumo_video.mp4",
        "generate": lambda c, nb: c.artifacts.generate_video(
            nb,
            instructions=INSTRUCOES_PADRAO,
            language="pt_BR",
            video_format=VideoFormat.EXPLAINER,
        ),
        "download": lambda c, nb, artifact_id, path: c.artifacts.download_video(
            nb, path, artifact_id
        ),
    },
    "4": {
        "label": "Slides (apresentação)",
        "filename": "resumo_slides.pdf",
        "generate": lambda c, nb: c.artifacts.generate_slide_deck(
            nb,
            instructions=INSTRUCOES_PADRAO,
            language="pt_BR",
            slide_format=SlideDeckFormat.PRESENTER_SLIDES,
        ),
        "download": lambda c, nb, artifact_id, path: c.artifacts.download_slide_deck(
            nb, path, artifact_id, output_format="pdf"
        ),
    },
    "5": {
        "label": "Quiz",
        "filename": "resumo_quiz.json",
        # generate_quiz não tem parâmetro "language"
        "generate": lambda c, nb: c.artifacts.generate_quiz(
            nb,
            instructions=INSTRUCOES_PADRAO,
            quantity=QuizQuantity.STANDARD,
            difficulty=QuizDifficulty.MEDIUM,
        ),
        "download": lambda c, nb, artifact_id, path: c.artifacts.download_quiz(
            nb, path, artifact_id, output_format="json"
        ),
    },
    "6": {
        "label": "Flashcards",
        "filename": "resumo_flashcards.json",
        # generate_flashcards também não tem parâmetro "language"
        "generate": lambda c, nb: c.artifacts.generate_flashcards(
            nb,
            instructions=INSTRUCOES_PADRAO,
            quantity=QuizQuantity.STANDARD,
            difficulty=QuizDifficulty.MEDIUM,
        ),
        "download": lambda c, nb, artifact_id, path: c.artifacts.download_flashcards(
            nb, path, artifact_id, output_format="json"
        ),
    },
    "7": {
        "label": "Resumo escrito (relatório / guia de estudos)",
        "filename": "resumo_escrito.md",
        "generate": lambda c, nb: c.artifacts.generate_report(
            nb,
            report_format=ReportFormat.STUDY_GUIDE,
            extra_instructions=INSTRUCOES_PADRAO,
            language="pt_BR",
        ),
        "download": lambda c, nb, artifact_id, path: c.artifacts.download_report(
            nb, path, artifact_id
        ),
    },
}


def escolher_formatos() -> list[str]:
    """Mostra o menu no terminal e devolve as chaves escolhidas pelo usuário."""
    print("Quais tipos de resumos você deseja gerar?\n")
    for chave, spec in ARTIFACT_SPECS.items():
        print(f"  {chave}) {spec['label']}")

    bruto = input(
        "\nDigite os números desejados separados por vírgula (ex: 1,2,5): "
    )
    escolhidos = [item.strip() for item in bruto.split(",") if item.strip()]

    invalidos = [c for c in escolhidos if c not in ARTIFACT_SPECS]
    if invalidos:
        print(f"Ignorando opções inválidas: {', '.join(invalidos)}")

    return [c for c in escolhidos if c in ARTIFACT_SPECS]

#função async como demonstrada no exemplo do github
async def main():
    escolhidos = escolher_formatos()
    if not escolhidos:
        print("Nenhum formato válido selecionado. Encerrando programa.")
        return

    async with NotebookLMClient.from_storage() as client:
        #Pergunta a fonte que será utilizada(link)
        fonte = input("Insira a fonte a ser utilizada no resumo: ")
        
        #Cria notebook e adiciona a fonte
        notebook = await client.notebooks.create("Estudo - Resumos Automáticos")
        print(f"\nNotebook criado: {notebook.id}")

        await client.sources.add_url(
            notebook.id,
            fonte,
            wait=True,  #Espera o NotebookLM terminar de indexar a fonte
        )
        print("Fonte adicionada e processada.\n")

        #Inicia a geração de cada formato escolhido
        status_por_formato = {}
        for chave in escolhidos:
            spec = ARTIFACT_SPECS[chave]
            print(f"Iniciando geração: {spec['label']}...")
            status_por_formato[chave] = await spec["generate"](client, notebook.id)

        #Espera cada geração terminar (pode levar alguns minutos cada)
        print("\nAguardando a conclusão das gerações (pode levar alguns minutos)...")
        finais_por_formato = {}
        for chave, status in status_por_formato.items():
            finais_por_formato[chave] = await client.artifacts.wait_for_completion(
                notebook.id, status.task_id, timeout=900
            )

        #Baixar os arquivos finais para o dispositivo
        print()
        for chave, final in finais_por_formato.items():
            spec = ARTIFACT_SPECS[chave]
            if final.is_complete:
                caminho = await spec["download"](
                    client, notebook.id, final.task_id, spec["filename"]
                )
                print(f"{spec['label']} salvo em: {caminho}")
            else:
                print(f"Falha ao gerar {spec['label']}: {final.status} ({final.error})")


if __name__ == "__main__":
    asyncio.run(main())

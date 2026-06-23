# PFS_MoodlenotebookLM
Projeto de conclusão da disciplina de Fábrica de Software do curso de Engenharia de Computação

Esse projeto busca automatizar a criação de resumos por meio da IA notebookLM, usando materiais didáticos postados no Moodle e enviados ao Google Drive para isso


## PRÉ REQUISITOS
instalar as seguintes dependências para que o algoritmo possa funcionar da maneira desejada

    pip install "notebooklm-py[browser]"
    playwright install chromium

ou


    pip install notebooklm-py

e depois rodar o seguinte comando no terminal. ***Sem ele não é possível acessar seu login do notebooklm***

    notebooklm login





## PROMPTS UTILIZADOS
Durante o desenvolvimento desse projeto foram utilizados ferramentas de Inteligência Artificial para acelerar seu desenvolvimento e auxiliar os estudantes a lidar com questões avançadas a respeito do código, portanto, segue abaixo os prompts utilizados e em qual modelo foram utilizados

### Claude AI, Sonnet 4.6
Prompts utilizados como base desenvolvimento da parte de do código refente a logar e baixar arquivos do Moodle:

    1º: "olá claude, é possível que um script python acesse o seguinte site : "https://portalvirtual.unisc.br/moodle/login_unisc/", peça ao usuário para fazer login e depois baixe arquivos de blocos desejados nesse moodle?"

    2º: "seria possível rodar esse script mesmo em uma distribuição linux como o fedora, onde playwright não é suportado oficialmente?"


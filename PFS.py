import asyncio # Para poder utilizar funções assíncronas
import requests # Para poder utilizar requests em webscraping
from pathlib import Path # Para realizar varedura em pastas 

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
# Importações necessárias para acessar o moodle
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium import webdriver
import os
import re
import sys
import time
import shutil
import urllib.parse

# ── Importações obrigatórias ─────────────────────────────────────────────────
for pkg, install in [("selenium", "selenium"), ("bs4", "beautifulsoup4"), ("requests", "requests")]:
    try:
        __import__(pkg)
    except ImportError:
        sys.exit(f"❌  '{pkg}' não encontrado. Rode:  pip install {install}")

# Declaração de constantes 
INSTRUCOES_PADRAO = "Resuma os pontos principais do material de forma clara e objetiva."
MOODLE_BASE = "https://portalvirtual.unisc.br/moodle"
LOGIN_URL = f"{MOODLE_BASE}/login_unisc/"
DASHBOARD_URL = f"{MOODLE_BASE}/my/"
DOWNLOAD_DIR = Path("./downloads_unisc")
LOGIN_TIMEOUT = 180  # segundos que o usuário tem para fazer login
PASTA_FONTES = "./downloads_unisc"
INCLUIR_SUBPASTAS = True

# Extensões de arquivos aceitos para serem enviados para NotebookLM
EXTENSOES_ACEITAS = {
    ".pdf", ".txt", ".md", ".doc", ".docx", ".epub",
    ".mp3", ".wav", ".mp4", ".mov", ".png", ".jpg", ".jpeg",
}

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

# Acessa pasta e mostra arquivos elegiveis para ser enviado ao NotebookLM
def listar_arquivos_da_pasta(pasta: str, recursivo: bool, extensoes: set[str]) -> list[Path]:
    """Retorna todos os arquivos da pasta cujo sufixo está em 'extensoes'."""
    base = Path(pasta)
    if not base.is_dir():
        raise FileNotFoundError(f"Pasta não encontrada: {base.resolve()}")

    padrao = base.rglob("*") if recursivo else base.glob("*")
    return sorted(
        p for p in padrao
        if p.is_file() and p.suffix.lower() in extensoes
    )


# Função responsável por Criação do WebDriver (Firefox ou Chromium, com fallback automático)
def create_driver() -> webdriver.Remote:
    """
    Tenta criar um WebDriver na seguinte ordem:
      1. Firefox com geckodriver do sistema
      2. Chromium/Chrome com chromedriver do sistema
      3. Firefox via webdriver-manager (baixa o driver automaticamente)
      4. Chrome via webdriver-manager
    """
    if DOWNLOAD_DIR.exists():
        shutil.rmtree(DOWNLOAD_DIR)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    # ── Tentativa 1: Firefox nativo ──────────────────────────────────────
    try:
        opts = webdriver.FirefoxOptions()
        # Configura pasta de download automático
        opts.set_preference("browser.download.folderList", 2)
        opts.set_preference("browser.download.dir",
                            str(DOWNLOAD_DIR.resolve()))
        opts.set_preference("browser.helperApps.neverAsk.saveToDisk",
                            "application/pdf,application/zip,application/octet-stream,"
                            "application/vnd.ms-excel,application/msword,"
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
                            "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        driver = webdriver.Firefox(options=opts)
        print("🦊  Usando Firefox.")
        return driver
    except WebDriverException:
        pass

    # ── Tentativa 2: Chromium/Chrome nativo ──────────────────────────────
    try:
        opts = webdriver.ChromeOptions()
        prefs = {
            "download.default_directory": str(DOWNLOAD_DIR.resolve()),
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
        }
        opts.add_experimental_option("prefs", prefs)
        driver = webdriver.Chrome(options=opts)
        print("🌐  Usando Chromium/Chrome.")
        return driver
    except WebDriverException:
        pass

    # ── Tentativa 3: webdriver-manager para Firefox ───────────────────────
    try:
        from webdriver_manager.firefox import GeckoDriverManager
        from selenium.webdriver.firefox.service import Service as FService
        opts = webdriver.FirefoxOptions()
        driver = webdriver.Firefox(
            service=FService(GeckoDriverManager().install()),
            options=opts
        )
        print("🦊  Usando Firefox (driver baixado automaticamente).")
        return driver
    except Exception:
        pass

    # ── Tentativa 4: webdriver-manager para Chrome ────────────────────────
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service as CService
        opts = webdriver.ChromeOptions()
        driver = webdriver.Chrome(
            service=CService(ChromeDriverManager().install()),
            options=opts
        )
        print("🌐  Usando Chrome (driver baixado automaticamente).")
        return driver
    except Exception:
        pass

    sys.exit(
        "❌  Nenhum browser/driver encontrado.\n\n"
        "  Opção A – instale Firefox + geckodriver:\n"
        "    Fedora:  sudo dnf install firefox geckodriver\n"
        "    Ubuntu:  sudo apt install firefox firefox-geckodriver\n\n"
        "  Opção B – instale webdriver-manager (baixa o driver sozinho):\n"
        "    pip install webdriver-manager\n"
    )

# Helpers Gerais
def sanitize(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()[:120]


def to_absolute_url(href: str) -> str:
    """
    Converte um href relativo/absoluto do Moodle em URL completa,
    usando urljoin (evita duplicar '/moodle' quando o href já começa
    com '/moodle/...').
    """
    if not href:
        return href
    return urllib.parse.urljoin(MOODLE_BASE + "/", href)


_DRIVE_FILE_RE = re.compile(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)")
_DRIVE_OPEN_RE = re.compile(r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)")


def to_drive_direct_download(url: str) -> str | None:
    """
    Converte um link de visualização do Google Drive
    (drive.google.com/file/d/ID/view ou .../open?id=ID) em um link de
    download direto (drive.google.com/uc?export=download&id=ID).

    Só funciona para arquivos públicos/compartilhados por link e até
    um certo tamanho — arquivos grandes ou privados vão receber uma
    página de confirmação em vez do arquivo (tratado em download_file).
    Retorna None se a URL não for reconhecida como link de arquivo do Drive.
    """
    m = _DRIVE_FILE_RE.search(url) or _DRIVE_OPEN_RE.search(url)
    if not m:
        return None
    file_id = m.group(1)
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def fix_header_mojibake(text: str) -> str:
    """
    Corrige nomes vindos de Content-Disposition em UTF-8 que o 'requests'
    decodificou como Latin-1 (bug comum com o Google Drive). Se o texto já
    estava correto, o round-trip simplesmente falha e devolve sem alterar.
    """

    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def print_header(text: str):
    print(f"\n{'─' * 60}")
    print(f"  {text}")
    print(f"{'─' * 60}")


def choose_from_list(items: list[str], prompt: str) -> list[int]:
    """Exibe lista numerada e devolve os índices escolhidos."""
    for i, item in enumerate(items, 1):
        print(f"  [{i:3}] {item}")
    print()
    raw = input(prompt).strip()

    if raw.lower() in ("*", "todos", "all", ""):
        return list(range(len(items)))

    indices = []
    for part in re.split(r"[,\s]+", raw):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            indices.extend(range(int(a) - 1, int(b)))
        else:
            indices.append(int(part) - 1)
    return sorted(set(i for i in indices if 0 <= i < len(items)))

# Extração de dados do Moodle
def wait_for_login(driver) -> None:
    """
    Aguarda o login manual (incluindo 2FA), verificando a URL a cada segundo.
    Só avança quando a URL contém '/moodle/' e nenhum termo de autenticação.
    """

    AUTH_TERMS = ("login", "verify", "mfa", "totp",
                  "auth", "sso", "token", "saml")

    print(f"\n⏳  Aguardando login completo (incluindo 2FA)…")
    print(f"    Você tem {LOGIN_TIMEOUT} segundos.\n")

    deadline = time.time() + LOGIN_TIMEOUT
    last_printed = ""

    while time.time() < deadline:
        try:
            url = driver.current_url.lower()
        except WebDriverException:
            # Browser fechado pelo usuário
            sys.exit("\n❌  Browser fechado antes do login ser concluído.")

        in_moodle = "/moodle/" in url
        in_auth = any(term in url for term in AUTH_TERMS)

        # Feedback dinâmico no terminal
        if any(term in url for term in ("login",)):
            status = "🔑  Aguardando usuário e senha…"
        elif any(term in url for term in ("verify", "mfa", "totp", "token", "saml")):
            status = "📱  Aguardando verificação em dois fatores (2FA)…"
        elif any(term in url for term in ("sso", "auth")):
            status = "🔄  Processando autenticação SSO…"
        elif in_moodle and not in_auth:
            # ✅ Chegamos em uma página real do Moodle
            print(f"\r    ✅  Login completo detectado!{' ' * 30}")
            return
        else:
            status = "⏳  Processando…"

        if status != last_printed:
            print(f"\r    {status}", end="", flush=True)
            last_printed = status

        time.sleep(1)

    # Tempo esgotado
    driver.quit()
    sys.exit("\n⏰  Tempo de login esgotado. Execute o script novamente.")


def get_enrolled_courses(driver) -> list[dict]:
    """Retorna cursos matriculados a partir do dashboard."""
    driver.get(DASHBOARD_URL)
    time.sleep(2)  # aguarda JS do dashboard carregar
    soup = BeautifulSoup(driver.page_source, "html.parser")

    seen_urls = set()
    courses = []
    for a in soup.select("a[href*='/course/view.php']"):
        name = a.get_text(separator=" ", strip=True)
        href = a.get("href", "")
        if not href.startswith("http"):
            href = to_absolute_url(href)
        if name and href not in seen_urls:
            seen_urls.add(href)
            courses.append({"name": name, "url": href})

    return courses


# Seletores de recurso "ativável" — qualquer link de atividade do Moodle,
# não só mod/resource. O tema atual da UNISC usa principalmente mod/url e
# mod/forum, mas outros tipos (assign, page, quiz, etc.) também devem ser
# capturados para não perder material.
_RESOURCE_SELECTORS = (
    "a[href*='mod/resource'], a[href*='mod/folder'], "
    "a[href*='mod/url'], a[href*='mod/page'], "
    "a[href*='mod/assign'], a[href*='mod/forum'], "
    "a[href*='mod/quiz'], a[href*='mod/choice'], "
    "a[href*='mod/lesson'], a[href*='mod/h5pactivity'], "
    "a[href*='pluginfile']"
)


def _extract_section_data(sec) -> dict:
    """Extrai título e recursos de um elemento de seção (BeautifulSoup tag)."""
    title_el = sec.select_one(
        ".sectionname, .section-title h3, h3.sectionname")
    title = title_el.get_text(strip=True) if title_el else "Sem título"

    resources = []
    for a in sec.select(_RESOURCE_SELECTORS):
        res_name = a.get_text(separator=" ", strip=True) or "recurso"
        res_url = a.get("href", "")
        if not res_url:
            continue
        if not res_url.startswith("http"):
            res_url = to_absolute_url(res_url)
        if res_url not in [r["url"] for r in resources]:
            resources.append({"name": res_name, "url": res_url})

    return {"title": title, "resources": resources}


def get_course_sections(driver, course_url: str) -> list[dict]:
    """
    Retorna seções (blocos) e seus recursos de um curso.

    O tema atual do Moodle só carrega o HTML da seção "ativa" — as demais
    ficam como <li> vazias (display:none). Por isso navegamos seção por
    seção usando &section=N, forçando o Moodle a carregar cada uma.
    """

    # 1ª carga: só para descobrir quantas seções existem (via data-section)
    driver.get(course_url)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    section_nums = sorted({
        int(sec["data-section"])
        for sec in soup.select("li.section.main[data-section]")
        if sec.get("data-section", "").isdigit()
    })

    if not section_nums:
        # Fallback: nenhum data-section encontrado, tenta extrair direto
        # (cobre cursos com formato antigo, sem lazy-load)
        return [
            _extract_section_data(sec)
            for sec in soup.select("li.section.main, li[id^='section-']")
        ]

    sep = "&" if "?" in course_url else "?"
    sections = []
    total = len(section_nums)

    for idx, n in enumerate(section_nums, 1):
        print(f"    🔄  Carregando seção {idx}/{total}…", end="\r", flush=True)
        section_url = f"{course_url}{sep}section={n}"
        driver.get(section_url)
        time.sleep(1.5)
        sec_soup = BeautifulSoup(driver.page_source, "html.parser")

        sec_el = sec_soup.select_one(
            f"li[data-section='{n}'], li#section-{n}")
        if sec_el is None:
            sections.append({"title": f"Seção {n}", "resources": []})
            continue

        data = _extract_section_data(sec_el)
        if data["title"] == "Sem título":
            data["title"] = f"Seção {n}"
        sections.append(data)

    print(" " * 40, end="\r")  # limpa a linha de progresso
    return sections


# ═══════════════════════════════════════════════════════════════════════════
# Sessão requests (reutiliza cookies do Selenium)
# ═══════════════════════════════════════════════════════════════════════════

def build_session(driver) -> requests.Session:
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"])
    session.headers["User-Agent"] = driver.execute_script(
        "return navigator.userAgent;")
    return session


def extract_page_links(driver, page_url: str) -> list[dict]:
    """
    Para mod/page (página de conteúdo com texto + links embutidos):
    abre a página e extrai todos os links encontrados no corpo do
    conteúdo (region 'page-content' ou, na falta dela, o <main> da
    página). Cada link é tratado como um "recurso" próprio — pode ser
    um arquivo (pluginfile), um link externo, ou outro mod/* do Moodle.
    """
    driver.get(page_url)
    time.sleep(1.5)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    container = (
        soup.select_one("[role='main'] .box.generalbox")
        or soup.select_one(".page-content")
        or soup.select_one("[role='main']")
        or soup
    )

    links = []
    for a in container.select("a[href]"):
        href = a.get("href", "")
        if not href or href.startswith("#"):
            continue
        name = a.get_text(separator=" ", strip=True) or "link"
        abs_url = href if href.startswith("http") else to_absolute_url(href)
        if abs_url not in [l["url"] for l in links]:
            links.append({"name": name, "url": abs_url})

    return links


def resolve_real_url(driver, resource_url: str) -> str | None:
    """
    Descobre a URL real de um mod/resource ou mod/url: segue redirect
    (pluginfile ou link externo) ou procura o link de arquivo na página
    intermediária, nessa ordem de prioridade.
    """

    driver.get(resource_url)
    time.sleep(1.5)

    current = driver.current_url
    if current and current != resource_url and (
        "pluginfile" in current or MOODLE_BASE not in current
    ):
        return current

    soup = BeautifulSoup(driver.page_source, "html.parser")
    for sel in [
        "a[href*='pluginfile']",
        "a[href*='forcedownload=1']",
        ".resourceworkaround a",
        "object[data*='pluginfile']",
        "iframe[src*='pluginfile']",
        "embed[src*='pluginfile']",
    ]:
        el = soup.select_one(sel)
        if el:
            href = el.get("href") or el.get("data") or el.get("src", "")
            if href:
                return href if href.startswith("http") else to_absolute_url(href)

    # Último recurso: procura qualquer URL de pluginfile no HTML bruto,
    # mesmo que não esteja num atributo padrão de link (ex: dentro de
    # um <script> com configuração JS do player/viewer do Moodle).
    match = re.search(
        r'["\']([^"\']*pluginfile\.php[^"\']*)["\']', driver.page_source)
    if match:
        href = match.group(1)
        return href if href.startswith("http") else to_absolute_url(href)

    # Nenhuma estratégia funcionou — mostra a URL onde paramos, pra
    # facilitar diagnóstico se isso continuar acontecendo.
    print(f"        🔍  Não achei link de arquivo. Parei em: {current}")
    return None


_SCRIPT_EXTENSIONS = {"php", "html", "htm", "asp", "aspx", "jsp"}


def _guess_extension_from_content_type(content_type: str) -> str | None:
    """Mapeia Content-Type comuns do Moodle para uma extensão de arquivo."""
    ct = content_type.split(";")[0].strip().lower()
    mapping = {
        "application/pdf": "pdf",
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.ms-excel": "xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/vnd.ms-powerpoint": "ppt",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
        "application/zip": "zip",
        "image/jpeg": "jpg",
        "image/png": "png",
        "text/plain": "txt",
        "text/csv": "csv",
    }
    return mapping.get(ct)


def _resolve_drive_confirm_page(session: requests.Session, resp, url: str):
    """
    Quando o Google Drive devolve a página de aviso 'arquivo grande,
    sem verificação de vírus' em vez do arquivo, tenta refazer a
    requisição de duas formas (nessa ordem):
      1. Extraindo o token real de confirm=TOKEN da página, se existir.
      2. Usando confirm=t (valor genérico que o Drive aceita atualmente
         para esse fluxo, já que os cookies de sessão já identificam
         a confirmação do aviso).
    Retorna uma nova response ou None se nada funcionar.
    """
    if "drive.google.com" not in url:
        return None

    m_id = _DRIVE_FILE_RE.search(url) or re.search(r"id=([a-zA-Z0-9_-]+)", url)
    if not m_id:
        return None
    file_id = m_id.group(1)

    html_preview = resp.text[:50_000] if hasattr(resp, "text") else ""

    confirm_values = []
    m = re.search(r'confirm=([0-9A-Za-z_-]+)', html_preview)
    if m:
        confirm_values.append(m.group(1))
    confirm_values.append("t")  # fallback genérico do fluxo atual do Drive

    for confirm_token in confirm_values:
        new_url = (f"https://drive.google.com/uc?export=download"
                   f"&confirm={confirm_token}&id={file_id}")
        try:
            retry = session.get(new_url, allow_redirects=True,
                                stream=True, timeout=120)
            if "text/html" not in retry.headers.get("Content-Type", "").lower():
                return retry
        except Exception:
            continue
    return None


def download_file(session: requests.Session, url: str, dest_dir: Path, fallback_name: str):
    """Baixa um arquivo e salva em dest_dir."""
    try:
        resp = session.get(url, allow_redirects=True, stream=True, timeout=120)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")

        # Se o servidor devolveu uma página HTML, provavelmente não é o
        # arquivo de fato. No caso do Google Drive, pode ser a página de
        # confirmação para arquivos grandes — tenta resolver antes de desistir.
        if "text/html" in content_type.lower():
            retry_resp = _resolve_drive_confirm_page(session, resp, url)
            if retry_resp is not None:
                resp = retry_resp
                content_type = resp.headers.get("Content-Type", "")
            else:
                print(f"    ⚠️  Resposta veio como HTML (não é o arquivo direto) "
                      f"para '{fallback_name}'. Link: {url}")
                return

        # Nome real pelo cabeçalho Content-Disposition
        cd = resp.headers.get("Content-Disposition", "")
        fname_match = re.search(r'filename[^;=\n]*=(["\']?)([^"\'\n;]+)\1', cd)
        fname = None
        if fname_match:
            fname = urllib.parse.unquote(fname_match.group(2).strip())
            fname = fix_header_mojibake(fname)

        if not fname:
            url_fname = urllib.parse.unquote(
                url.split("?")[0].rstrip("/").split("/")[-1])
            ext = url_fname.rsplit(
                ".", 1)[-1].lower() if "." in url_fname else ""
            # Nomes terminados em extensão de script (.php, .html...) não
            # são nomes de arquivo reais — são o endpoint da página.
            if url_fname and "." in url_fname and ext not in _SCRIPT_EXTENSIONS:
                fname = url_fname
            else:
                guessed_ext = _guess_extension_from_content_type(content_type)
                base = sanitize(fallback_name)
                fname = f"{base}.{guessed_ext}" if guessed_ext else f"{base}.bin"

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / sanitize(fname)

        # Não rebaixa se o arquivo já existe e tem o mesmo tamanho
        content_length = int(resp.headers.get("Content-Length", 0))
        if dest_path.exists() and content_length and dest_path.stat().st_size == content_length:
            print(f"    ⏭️   Já existe: {fname}")
            return

        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=16_384):
                f.write(chunk)

        size_kb = dest_path.stat().st_size / 1024
        print(f"    ✅  {fname}  ({size_kb:.1f} KB)")

    except Exception as e:
        print(f"    ❌  Erro ao baixar '{fallback_name}': {e}")

#============================================================================
# FLUXO PRINCIPAL
#================================================================
def mainM():
    print_header("UNISC Moodle Downloader")
    print("  Abrirá o browser para você fazer login.")
    print("  Depois, escolha cursos e blocos para baixar.\n")

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    driver = create_driver()

    try:
        # ── 1. Login ───────────────────────────────────────────────────────
        driver.get(LOGIN_URL)
        wait_for_login(driver)

        # ── 2. Cursos ──────────────────────────────────────────────────────
        print_header("Buscando cursos…")
        courses = get_enrolled_courses(driver)

        if not courses:
            sys.exit(
                "❌  Nenhum curso encontrado. Verifique se o login foi bem-sucedido.")

        print_header("Seus cursos")
        chosen_ci = choose_from_list(
            [c["name"] for c in courses],
            "Escolha o(s) curso(s) [números, intervalos 1-3, ou * para todos]: "
        )

        # ── 3. Blocos e download ───────────────────────────────────────────
        session = build_session(driver)

        for ci in chosen_ci:
            course = courses[ci]
            print_header(f"Curso: {course['name']}")

            sections = get_course_sections(driver, course["url"])
            if not sections:
                print("  ⚠️  Nenhuma seção encontrada.")
                continue

            # Filtra seções sem recursos para exibição mais limpa
            sec_labels = [
                f"{s['title']}  ({len(s['resources'])} arquivo(s))"
                for s in sections
            ]
            chosen_si = choose_from_list(
                sec_labels,
                "Escolha os blocos [números, intervalos 1-3, ou * para todos]: "
            )

            for si in chosen_si:
                section = sections[si]
                sec_dir = DOWNLOAD_DIR / \
                    sanitize(course["name"]) / sanitize(section["title"])
                print(f"\n📂  Bloco: {section['title']}")

                if not section["resources"]:
                    print("    ⚠️  Sem recursos diretos neste bloco.")
                    continue

                for res in section["resources"]:
                    url = res["url"]

                    # Fóruns, questionários, escolhas e lições não são
                    # arquivos — são páginas/atividades do Moodle. Pular.
                    if any(tipo in url for tipo in (
                        "mod/forum", "mod/quiz", "mod/choice",
                        "mod/lesson", "mod/assign"
                    )):
                        print(f"    ⏭️   Pulando atividade (não é arquivo): "
                              f"'{res['name']}'")
                        continue

                    # mod/page é uma página de texto com links embutidos.
                    # Abrimos e processamos cada link encontrado dentro dela.
                    if "mod/page" in url:
                        print(f"    📄  Página '{res['name']}' — abrindo para "
                              f"extrair links internos…")
                        inner_links = extract_page_links(driver, url)
                        if not inner_links:
                            print(
                                f"        ⚠️  Nenhum link encontrado dentro da página.")
                        for link in inner_links:
                            link_url = link["url"]
                            if "colab.research.google.com" in link_url:
                                print(f"        🔗  Notebook Colab: "
                                      f"'{link['name']}' → {link_url}")
                                continue
                            drive_url = to_drive_direct_download(link_url)
                            if drive_url:
                                download_file(session, drive_url,
                                              sec_dir, link["name"])
                                continue
                            if "pluginfile" in link_url or re.search(
                                r"\.(pdf|docx?|xlsx?|pptx?|zip|rar|7z|txt|csv|jpg|jpeg|png)(\?|$)",
                                link_url, re.IGNORECASE
                            ):
                                download_file(session, link_url,
                                              sec_dir, link["name"])
                            else:
                                print(f"        🔗  Link externo: "
                                      f"'{link['name']}' → {link_url}")
                        continue

                    # mod/url pode ser um link externo (ex: Google Meet,
                    # YouTube, Colab) OU um redirecionamento para um
                    # arquivo (PDF, slide, etc). Trata caso a caso.
                    if "mod/url" in url:
                        real_url = resolve_real_url(driver, url) or url

                        # Google Colab é um notebook interativo, não um
                        # arquivo para baixar — sempre listar como link.
                        if "colab.research.google.com" in real_url:
                            print(f"    🔗  Notebook Colab (abrir no navegador): "
                                  f"'{res['name']}' → {real_url}")
                            continue

                        # Google Drive: converte para link de download direto
                        drive_url = to_drive_direct_download(real_url)
                        if drive_url:
                            download_file(session, drive_url,
                                          sec_dir, res["name"])
                            continue

                        # Heurística por extensão para os demais casos
                        if re.search(r"\.(pdf|docx?|xlsx?|pptx?|zip|rar|7z|txt|csv|jpg|jpeg|png)(\?|$)",
                                     real_url, re.IGNORECASE):
                            download_file(session, real_url,
                                          sec_dir, res["name"])
                        else:
                            print(f"    🔗  Link externo (não é arquivo), "
                                  f"pulando: '{res['name']}' → {real_url}")
                        continue

                    # Recursos mod/resource e mod/folder têm página intermediária
                    if "mod/resource" in url or "mod/folder" in url:
                        real_url = resolve_real_url(driver, url)
                        if real_url:
                            download_file(session, real_url,
                                          sec_dir, res["name"])
                        else:
                            print(
                                f"    ⚠️  Link direto não encontrado para '{res['name']}'")
                    else:
                        download_file(session, url, sec_dir, res["name"])

    finally:
        driver.quit()

    print_header("Concluído!")
    print(f"  📁  Arquivos em: {DOWNLOAD_DIR.resolve()}\n")



#função async como demonstrada no exemplo do github
async def main():
    escolhidos = escolher_formatos()
    if not escolhidos:
        print("Nenhum formato válido selecionado. Encerrando programa.")
        return

    arquivos = listar_arquivos_da_pasta(PASTA_FONTES, INCLUIR_SUBPASTAS, EXTENSOES_ACEITAS)
    if not arquivos:
        print(f"Nenhum arquivo compatível encontrado em '{PASTA_FONTES}'.")
        return
    print(f"{len(arquivos)} arquivo(s) encontrado(s) em '{PASTA_FONTES}':")
    for a in arquivos:
        print(f"  - {a.name}")

    async with NotebookLMClient.from_storage() as client:
        #Cria notebook e adiciona a fonte
        notebook = await client.notebooks.create("Estudo - Resumos Automáticos")
        print(f"\nNotebook criado: {notebook.id}")

        # Envia arquivos para NotebookLM
        for caminho in arquivos:
            print(f"Enviando '{caminho.name}'...")
            await client.sources.add_file(notebook.id, str(caminho), wait=True)

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
    mainM()
    asyncio.run(main())

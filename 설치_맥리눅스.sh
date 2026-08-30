#!/bin/bash
echo "============================================"
echo "  AGI - 한 번에 설치 (맥/리눅스)"
echo "  파이썬부터 브라우저까지 알아서 설치합니다."
echo "============================================"
echo

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${AGI_INSTALL_DIR:-$SCRIPT_DIR/programs}"
echo "프로그램 설치 경로: $INSTALL_DIR"
echo

# ── 1) 파이썬 확인, 없으면 자동 설치 ──
if ! command -v python3 &> /dev/null; then
  echo "[1/4] 파이썬이 없습니다. 자동 설치를 시도합니다..."
  if [[ "$OSTYPE" == "darwin"* ]]; then
    # 맥: brew
    if command -v brew &> /dev/null; then
      brew install python
    else
      echo "[!] Homebrew가 없습니다. 먼저 설치하세요:"
      echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
      echo "    그 다음 이 파일을 다시 실행하세요."
      exit 1
    fi
  else
    # 리눅스: apt
    if command -v apt &> /dev/null; then
      sudo apt update && sudo apt install -y python3 python3-pip
    else
      echo "[!] apt가 없습니다. 배포판에 맞게 python3 python3-pip 를 설치 후 다시 실행하세요."
      exit 1
    fi
  fi
fi

if ! command -v python3 &> /dev/null; then
  echo "[!] 파이썬 설치에 실패했습니다. 수동 설치 후 다시 실행하세요."
  exit 1
fi
echo "[1/4] 파이썬 확인됨: $(python3 --version)"

# ── 2) pip ──
echo "[2/4] pip 준비 중..."
python3 -m pip install --upgrade pip >/dev/null 2>&1

# ── 3) 패키지 ──
echo "[3/4] 패키지 설치 중 (Pillow numpy kollocate playwright pytesseract)..."
python3 -m pip install Pillow numpy kollocate playwright pytesseract || {
  echo "[!] 패키지 설치 실패. 인터넷 확인 후 다시 실행하세요."; exit 1; }

# ── 4) 브라우저 ──
echo "[4/4] 브라우저(chromium) 설치 중... (조금 큽니다)"
export PLAYWRIGHT_BROWSERS_PATH="$INSTALL_DIR/browsers"
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
python3 -m playwright install chromium

echo
echo "[+] (선택) 화면을 사람처럼 보기(OCR): Tesseract 설치"
echo "    맥:    brew install tesseract tesseract-lang"
echo "    우분투: sudo apt install tesseract-ocr tesseract-ocr-kor"
echo "    설치 후 config.py 의 SEE_LIKE_HUMAN 을 True 로."
echo
echo "============================================"
echo "  설치 끝!  실행:  python3 server.py"
echo "  브라우저에서  http://localhost:8000"
echo "  (처음 켤 때 사전 받느라 1~2분 걸립니다)"
echo "============================================"
echo "자세한 사용/검증 방법은 '검증_가이드.txt' 를 보세요."

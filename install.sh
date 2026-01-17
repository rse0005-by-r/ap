#!binbash

# Универсальный установщик приложения
# Работает на Linux (UbuntuDebianArch), macOS, Git Bash на Windows

set -e  # Выход при ошибке

# Цвета для вывода
RED='033[0;31m'
GREEN='033[0;32m'
YELLOW='033[1;33m'
NC='033[0m' # No Color

echo -e ${GREEN}=== Установка приложения ===${NC}

# Определение ОС и менеджера пакетов
detect_os() {
    case $(uname -s) in
        Linux)
            if [ -f etcdebian_version ]; then
                echo debian  # Ubuntu, Debian
            elif [ -f etcarch-release ]; then
                echo arch    # Arch, Manjaro
            elif [ -f etcredhat-release ]; then
                echo rpm     # Fedora, CentOS
            else
                echo linux
            fi
            ;;
        Darwin)
            echo macos       # macOS
            ;;
        MINGWMSYSCYGWIN)
            echo windows     # Git Bash на Windows
            ;;
        )
            echo unknown
            ;;
    esac
}

# Установка зависимостей
install_dependencies() {
    local os=$(detect_os)
    
    echo -e ${YELLOW}Установка зависимостей для $os...${NC}
    
    case $os in
        debian)
            sudo apt-get update
            sudo apt-get install -y git python3 python3-pip nodejs npm curl wget
            ;;
        arch)
            sudo pacman -Sy --noconfirm git python python-pip nodejs npm curl wget
            ;;
        rpm)
            sudo dnf install -y git python3 python3-pip nodejs npm curl wget
            ;;
        macos)
            # Проверка наличия Homebrew
            if ! command -v brew & devnull; then
                echo -e ${YELLOW}Установка Homebrew...${NC}
                binbash -c $(curl -fsSL httpsraw.githubusercontent.comHomebrewinstallHEADinstall.sh)
            fi
            brew install git python node curl wget
            ;;
        windows)
            echo -e ${YELLOW}Для Windows убедитесь, что установлены${NC}
            echo 1. Git Bash httpsgitforwindows.org
            echo 2. Python 3 httpswww.python.orgdownloads
            echo 3. Node.js httpsnodejs.org
            read -p Нажмите Enter после установки...
            ;;
    esac
}

# Клонирование или обновление репозитория
setup_repository() {
    local repo_url=httpsgithub.comrse0005-by-rap.git
    local repo_dir=ap-app
    
    if [ -d $repo_dir ]; then
        echo -e ${YELLOW}Обновление существующего репозитория...${NC}
        cd $repo_dir
        git pull origin main
    else
        echo -e ${YELLOW}Клонирование репозитория...${NC}
        git clone $repo_url $repo_dir
        cd $repo_dir
    fi
}

# Настройка виртуального окружения Python
setup_python_env() {
    echo -e ${YELLOW}Настройка Python окружения...${NC}
    
    # Создание виртуального окружения
    python3 -m venv venv 2devnull  python -m venv venv 2devnull  {
        echo -e ${YELLOW}Установка virtualenv...${NC}
        pip3 install virtualenv  pip install virtualenv
        virtualenv venv
    }
    
    # Активация в зависимости от ОС
    if [[ $OSTYPE == msys  $OSTYPE == cygwin ]]; then
        # Windows Git Bash
        source venvScriptsactivate
    else
        # LinuxmacOS
        source venvbinactivate
    fi
    
    # Установка Python зависимостей
    if [ -f requirements.txt ]; then
        pip install -r requirements.txt
    elif [ -f apprequirements.txt ]; then
        pip install -r apprequirements.txt
    fi
}

# Настройка Node.js проекта
setup_node_env() {
    if [ -f package.json ]  [ -f apppackage.json ]; then
        echo -e ${YELLOW}Настройка Node.js проекта...${NC}
        
        local pkg_file=package.json
        [ -f apppackage.json ] && pkg_file=apppackage.json
        
        npm install  {
            echo -e ${YELLOW}Пробую с yarn...${NC}
            if command -v yarn & devnull; then
                yarn install
            else
                npm install --legacy-peer-deps
            fi
        }
    fi
}

# Создание универсального скрипта запуска
create_launcher() {
    echo -e ${YELLOW}Создание скрипта запуска...${NC}
    
    cat  start.sh  'EOF'
#!binbash

# Универсальный скрипт запуска приложения

set -e

# Определение пути к виртуальному окружению
VENV_DIR=venv
if [ ! -d $VENV_DIR ]; then
    VENV_DIR=appvenv
fi

# Активация Python окружения
if [[ $OSTYPE == msys  $OSTYPE == cygwin ]]; then
    # Windows
    if [ -f $VENV_DIRScriptsactivate ]; then
        source $VENV_DIRScriptsactivate
    fi
else
    # LinuxmacOS
    if [ -f $VENV_DIRbinactivate ]; then
        source $VENV_DIRbinactivate
    fi
fi

# Запуск приложения
if [ -f main.py ]; then
    python main.py
elif [ -f appmain.py ]; then
    python appmain.py
elif [ -f app.py ]; then
    python app.py
elif [ -f index.js ]; then
    node index.js
elif [ -f appindex.js ]; then
    node appindex.js
else
    echo Точка входа не найдена
    echo Доступные файлы
    ls -la  grep -E .(pyjssh)$
    exit 1
fi
EOF

    chmod +x start.sh
    
    # Для Windows также создаем .bat файл
    if [[ $OSTYPE == msys  $OSTYPE == cygwin ]]; then
        cat  start.bat  'EOF'
@echo off
REM Бат-файл для запуска на Windows

if exist venvScriptsactivate.bat (
    call venvScriptsactivate.bat
) else if exist appvenvScriptsactivate.bat (
    call appvenvScriptsactivate.bat
)

if exist main.py (
    python main.py
) else if exist appmain.py (
    python appmain.py
) else if exist app.py (
    python app.py
) else if exist index.js (
    node index.js
) else if exist appindex.js (
    node appindex.js
) else (
    echo Точка входа не найдена
    dir b .py .js
    pause
)
EOF
    fi
}

# Основной процесс установки
main() {
    echo -e ${GREEN}Проверка системы...${NC}
    
    # Проверка наличия git
    if ! command -v git & devnull; then
        install_dependencies
    fi
    
    setup_repository
    setup_python_env
    setup_node_env
    create_launcher
    
    echo -e ${GREEN}✅ Установка завершена!${NC}
    echo -e ${YELLOW}Для запуска приложения выполните${NC}
    echo cd ap-app
    echo .start.sh
    echo 
    echo -e ${YELLOW}Или для Windows${NC}
    echo cd ap-app
    echo start.bat
}

# Запуск основной функции
main $@
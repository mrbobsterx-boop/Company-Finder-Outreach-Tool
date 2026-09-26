#!/usr/bin/env bash
# One-time setup: adds a "Company Finder & Outreach" icon to the desktop
# application menu (and to ~/Desktop, if it exists) so the tool can be
# launched with a double-click instead of typing commands in a terminal.
#
# Run this once from inside the project folder:
#   ./install_launcher.sh
set -e
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

mkdir -p "$HOME/.local/share/applications"
DESKTOP_FILE="$HOME/.local/share/applications/company-finder-outreach.desktop"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Company Finder & Outreach
Comment=Локальный интерфейс поиска компаний и рассылки
Exec=bash -c 'cd "$PROJECT_DIR" && ./run_gui.sh; echo; read -p "Нажмите Enter, чтобы закрыть это окно..."'
Icon=applications-internet
Terminal=true
Categories=Utility;
EOF
chmod +x "$DESKTOP_FILE"

if [ -d "$HOME/Desktop" ]; then
  cp "$DESKTOP_FILE" "$HOME/Desktop/company-finder-outreach.desktop"
  chmod +x "$HOME/Desktop/company-finder-outreach.desktop"
fi

echo "Готово!"
echo "Ярлык \"Company Finder & Outreach\" добавлен в меню приложений"
if [ -d "$HOME/Desktop" ]; then
  echo "и на рабочий стол."
fi
echo "При первом запуске система может спросить \"Доверять и запустить\" — это нормально, соглашайся."

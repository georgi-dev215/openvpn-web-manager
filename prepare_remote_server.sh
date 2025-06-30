#!/bin/bash

# 🚀 Скрипт подготовки удаленного сервера для кластера OpenVPN
# Запустите этот скрипт на каждом сервере, который хотите добавить в кластер

set -e

echo "🚀 Подготовка сервера для кластера OpenVPN..."

# Обновление системы
echo "📦 Обновление системы..."
apt update && apt upgrade -y

# Установка необходимых пакетов
echo "📦 Установка пакетов..."
apt install -y curl wget openssh-server ufw

# Проверка и установка OpenVPN если не установлен
if ! command -v openvpn &> /dev/null; then
    echo "🔧 OpenVPN не найден. Устанавливаем..."
    
    # Скачиваем скрипт установки
    curl -O https://raw.githubusercontent.com/angristan/openvpn-install/master/openvpn-install.sh
    chmod +x openvpn-install.sh
    
    echo "⚠️  ВАЖНО: Запустите ./openvpn-install.sh вручную и настройте OpenVPN!"
    echo "После настройки OpenVPN запустите этот скрипт снова."
    exit 1
else
    echo "✅ OpenVPN уже установлен"
fi

# Проверка работы OpenVPN
echo "🔍 Проверка состояния OpenVPN..."
if systemctl is-active --quiet openvpn-server@server; then
    echo "✅ OpenVPN сервер работает"
else
    echo "❌ OpenVPN сервер не запущен. Запускаем..."
    systemctl enable openvpn-server@server
    systemctl start openvpn-server@server
fi

# Проверка Easy-RSA
echo "🔍 Проверка Easy-RSA..."
if [ -d "/etc/openvpn/server/easy-rsa" ]; then
    echo "✅ Easy-RSA найден"
    
    # Проверка PKI
    if [ -d "/etc/openvpn/server/easy-rsa/pki" ]; then
        echo "✅ PKI инициализирован"
    else
        echo "❌ PKI не инициализирован!"
    fi
    
    if [ -d "/etc/openvpn/server/easy-rsa/pki/issued" ]; then
        echo "✅ Директория сертификатов найдена"
        echo "📋 Существующие клиенты:"
        ls /etc/openvpn/server/easy-rsa/pki/issued/ | grep -v server | sed 's/.crt$//' || echo "Нет клиентов"
    fi
else
    echo "❌ Easy-RSA не найден!"
    exit 1
fi

# Настройка SSH
echo "🔐 Настройка SSH..."

# Разрешить SSH подключения
systemctl enable ssh
systemctl start ssh

# Создание директории для SSH ключей если не существует
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# Настройка SSH конфигурации
SSH_CONFIG="/etc/ssh/sshd_config"
cp $SSH_CONFIG ${SSH_CONFIG}.backup

# Разрешить подключение root (осторожно!)
sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' $SSH_CONFIG

# Разрешить аутентификацию по ключам
sed -i 's/#PubkeyAuthentication.*/PubkeyAuthentication yes/' $SSH_CONFIG

# По желанию - разрешить аутентификацию по паролю
read -p "🔑 Разрешить SSH аутентификацию по паролю? (y/n): " enable_password
if [[ $enable_password == "y" || $enable_password == "Y" ]]; then
    sed -i 's/#PasswordAuthentication.*/PasswordAuthentication yes/' $SSH_CONFIG
    echo "✅ Аутентификация по паролю разрешена"
else
    sed -i 's/#PasswordAuthentication.*/PasswordAuthentication no/' $SSH_CONFIG
    echo "✅ Аутентификация только по ключам"
fi

# Перезапуск SSH
systemctl restart sshd
echo "✅ SSH настроен и перезапущен"

# Настройка firewall
echo "🔥 Настройка firewall..."
ufw --force enable

# SSH
ufw allow ssh

# OpenVPN (обычно 1194/udp, но может отличаться)
OPENVPN_PORT=$(grep -E "^port " /etc/openvpn/server/server.conf | awk '{print $2}' || echo "1194")
OPENVPN_PROTO=$(grep -E "^proto " /etc/openvpn/server/server.conf | awk '{print $2}' || echo "udp")
ufw allow ${OPENVPN_PORT}/${OPENVPN_PROTO}
echo "✅ Разрешен OpenVPN на порту ${OPENVPN_PORT}/${OPENVPN_PROTO}"

# Показать состояние
ufw status

# Информация о сервере
echo ""
echo "🎉 Подготовка сервера завершена!"
echo ""
echo "📋 Информация о сервере:"
echo "------------------------"
echo "🖥️  IP адрес: $(curl -s ifconfig.me || hostname -I | awk '{print $1}')"
echo "🔧 OpenVPN статус: $(systemctl is-active openvpn-server@server)"
echo "🔐 SSH порт: $(grep -E "^#?Port " /etc/ssh/sshd_config | awk '{print $2}' || echo "22")"
echo "📁 Easy-RSA путь: /etc/openvpn/server/easy-rsa"
echo "📋 Клиентов: $(ls /etc/openvpn/server/easy-rsa/pki/issued/ 2>/dev/null | grep -v server | wc -l)"

echo ""
echo "🔑 Для SSH ключей:"
echo "Скопируйте публичный ключ с главного сервера:"
echo "ssh-copy-id -i ~/.ssh/cluster_key.pub root@$(curl -s ifconfig.me)"

echo ""
echo "✅ Сервер готов для добавления в кластер!"
echo "Теперь добавьте этот сервер через веб-интерфейс OpenVPN Manager" 
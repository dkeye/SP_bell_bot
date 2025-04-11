import hashlib
import os
import random
import re
import time
import requests

# Параметры подключения
ROUTER_IP = os.getenv("ROUTER_IP")
ROUTER_PASS = os.getenv("ROUTER_PASS")

# Кэш для хранения токена и времени его получения
_cached_token = None
_token_timestamp = None
TOKEN_CACHE_TIME = 300  # Время жизни токена в секундах


def fetch_router_login_page():
    """Получение страницы авторизации роутера."""
    response = requests.get(f"http://{ROUTER_IP}/cgi-bin/luci/web")
    if response.status_code != 200:
        print("Ошибка: Не удалось получить страницу входа в роутер.")
        return None
    return response.text


def extract_mac_and_nonce_key(page_content):
    """Извлечение MAC-адреса и nonce_key из страницы авторизации."""
    mac_match = re.search(r"var deviceId = \'(.*?)\'", page_content)
    nonce_key_match = re.search(r"key: \'(.*)\',", page_content)

    if not mac_match or not nonce_key_match:
        print("Ошибка: Не удалось извлечь MAC-адрес или nonce_key.")
        return None, None

    return mac_match.group(1), nonce_key_match.group(1)


def generate_nonce(mac_address):
    """Генерация nonce."""
    return f"0_{mac_address}_{int(time.time())}_{random.randint(1000, 10000)}"


def hash_password(password, nonce_key, nonce):
    """Хеширование пароля для авторизации."""
    hashed_password = hashlib.sha1((password + nonce_key).encode("utf-8")).hexdigest()
    final_password = hashlib.sha1((nonce + hashed_password).encode("utf-8")).hexdigest()
    return final_password


def request_token(mac_address, nonce, hashed_password):
    """Запрос токена авторизации у роутера."""
    login_data = {
        "username": "admin",
        "password": hashed_password,
        "logtype": "2",
        "nonce": nonce
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}

    response = requests.post(
        f"http://{ROUTER_IP}/cgi-bin/luci/api/xqsystem/login",
        data=login_data,
        headers=headers
    )

    if response.status_code != 200:
        print("Ошибка: Не удалось выполнить вход в роутер.")
        return None

    token_match = re.search(r'"token":"(.*?)"', response.text)
    if not token_match:
        print("Ошибка: Не удалось получить токен.")
        return None

    return token_match.group(1)


def router_login():
    """
    Авторизация на роутере и получение токена.
    Кэширует токен, если он ещё валиден.
    """
    global _cached_token, _token_timestamp

    # Если токен валиден, используем из кэша
    if _cached_token and _token_timestamp and (time.time() - _token_timestamp < TOKEN_CACHE_TIME):
        return _cached_token

    try:
        # 1. Получаем страницу авторизации и извлекаем нужные параметры
        page_content = fetch_router_login_page()
        if not page_content:
            return None

        mac_address, nonce_key = extract_mac_and_nonce_key(page_content)
        if not mac_address or not nonce_key:
            return None

        # 2. Генерируем nonce и хешируем пароль
        nonce = generate_nonce(mac_address)
        final_password = hash_password(ROUTER_PASS, nonce_key, nonce)

        # 3. Запрашиваем токен
        token = request_token(mac_address, nonce, final_password)
        if not token:
            return None

        # Кэшируем токен
        _cached_token = token
        _token_timestamp = time.time()
        return token

    except Exception as e:
        print(f"Ошибка в router_login: {e}")
        return None


def get_connected_devices(token):
    """Получение списка устройств, подключённых к роутеру."""
    try:
        response = requests.get(
            f"http://{ROUTER_IP}/cgi-bin/luci/;stok={token}/api/misystem/devicelist"
        )
        if response.status_code != 200:
            print("Ошибка: Не удалось получить список устройств.")
            return []

        data = response.json()
        return data.get("list", [])

    except Exception as e:
        print(f"Ошибка в get_connected_devices: {e}")
        return []


def get_connected_macs():
    """
    Получение MAC-адресов подключённых устройств.
    MAC-ы фильтруются только у онлайн-устройств.
    """
    token = router_login()
    if not token:
        return []

    devices = get_connected_devices(token)
    return [device["mac"] for device in devices if device.get("online") == 1]

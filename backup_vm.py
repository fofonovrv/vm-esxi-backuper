#!/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
import ssl
import getpass
import time
import warnings
import argparse
import shutil
import yaml
from datetime import datetime
from urllib.parse import urlparse
from webdav3.client import Client as WebDavClient
from webdav3.exceptions import NoConnection, ResponseErrorCode

# Подавляем предупреждение о небезопасном запросе
from urllib3.exceptions import InsecureRequestWarning
warnings.filterwarnings("ignore", category=InsecureRequestWarning)

from pyVim import connect
from pyVmomi import vim
from tqdm import tqdm

# --- Функции ---

def load_config(config_path):
    """Загружает конфигурацию из YAML-файла."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Файл конфигурации не найден: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    if not all(key in config for key in ['esxi', 'storage']):
        raise ValueError("В файле конфигурации отсутствуют обязательные секции: 'esxi', 'storage'.")
    return config

def check_nextcloud_access(nc_config):
    """Выполняет предварительную проверку доступа к Nextcloud."""
    options = {
        'webdav_hostname': nc_config['url'],
        'webdav_login': nc_config['user'],
        'webdav_password': nc_config['password']
    }
    client = WebDavClient(options)
    
    # 1. Проверка базового соединения и аутентификации
    try:
        client.info("/") # Запрашиваем информацию о корневом каталоге
    except NoConnection:
        raise ConnectionError("Не удалось подключиться к серверу Nextcloud. Проверьте URL.")
    except ResponseErrorCode as e:
        if e.code == 401:
            raise ConnectionRefusedError("Ошибка аутентификации в Nextcloud. Проверьте логин и пароль.")
        else:
            raise
    
    # 2. Проверка существования/создание удаленной папки
    remote_dir = nc_config['remote_dir']
    if not client.check(remote_dir):
        print(f"Папка '{remote_dir}' не найдена. Попытка создать...")
        client.mkdir(remote_dir)
        if not client.check(remote_dir):
            raise FileNotFoundError(f"Не удалось создать папку '{remote_dir}' на сервере Nextcloud.")

    # 3. Проверка прав на запись
    test_filename = f".write_test_{int(time.time())}.tmp"
    remote_test_path = os.path.join(remote_dir, test_filename)
    try:
        # Создаем пустой временный файл локально
        with open(test_filename, 'w') as f:
            pass
        # Пытаемся загрузить его
        client.upload_sync(remote_path=remote_test_path, local_path=test_filename)
    except Exception as e:
        raise PermissionError(f"Нет прав на запись в папку '{remote_dir}'. Ошибка: {e}")
    finally:
        # Гарантированно удаляем тестовые файлы
        if client.check(remote_test_path):
            client.clean(remote_test_path)
        if os.path.exists(test_filename):
            os.remove(test_filename)

def find_vm_by_name(content, vm_name):
    # (код функции без изменений)
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.VirtualMachine], True)
    for vm in container.view:
        if vm.name == vm_name:
            return vm
    return None

def download_file_with_progress(url, local_path, session, total_size):
    # (код функции без изменений)
    try:
        response = session.get(url, stream=True, verify=False)
        response.raise_for_status()
        block_size = 1024 * 1024
        print(f"  -> Скачивание {os.path.basename(local_path)} ({total_size / (1024*1024):.2f} MB)")
        with open(local_path, 'wb') as f, tqdm(
            total=total_size, unit='B', unit_scale=True, desc="  "
        ) as bar:
            for data in response.iter_content(block_size):
                bar.update(len(data))
                f.write(data)
        return True
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при скачивании файла: {e}")
        return False

def upload_to_nextcloud(local_file, nc_config):
    # (код функции без изменений)
    options = {
        'webdav_hostname': nc_config['url'],
        'webdav_login': nc_config['user'],
        'webdav_password': nc_config['password']
    }
    client = WebDavClient(options)
    remote_path = os.path.join(nc_config['remote_dir'], os.path.basename(local_file))
    print(f"Загрузка архива в Nextcloud: {remote_path}...")
    client.upload_sync(remote_path=remote_path, local_path=local_file)
    print("Загрузка в облако успешно завершена.")


# --- Основная логика ---

def main():
    parser = argparse.ArgumentParser(description="Скрипт для бэкапа ВМ с ESXi хоста.")
    parser.add_argument('--config', required=True, help="Путь к файлу конфигурации config.yaml.")
    parser.add_argument('--vm-name', required=True, help="Имя виртуальной машины для бэкапа.")
    parser.add_argument('--destination', required=True, choices=['file', 'cloud'], help="Место назначения бэкапа.")
    args = parser.parse_args()

    config = load_config(args.config)
    esxi_cfg = config['esxi']
    storage_cfg = config['storage']
    
    # ================== НОВАЯ ПРЕДВАРИТЕЛЬНАЯ ПРОВЕРКА ==================
    if args.destination == 'cloud':
        print("Выбрана загрузка в облако. Выполняется предварительная проверка доступа...")
        try:
            if 'nextcloud' not in config:
                raise ValueError("Секция 'nextcloud' отсутствует в конфиге.")
            check_nextcloud_access(config['nextcloud'])
            print("✅ Доступ к Nextcloud и права на запись подтверждены.")
        except Exception as e:
            print(f"❌ Ошибка проверки доступа к Nextcloud: {e}")
            print("Процесс бэкапа прерван.")
            return # Прерываем выполнение
    # ====================================================================

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    vm_backup_path = os.path.join(storage_cfg['local_backup_dir'], f"{args.vm_name.replace(' ', '_')}_{timestamp}")
    
    service_instance = None
    lease = None

    try:
        # --- Подключение и экспорт ВМ (остальная логика) ---
        print(f"Подключение к хосту {esxi_cfg['host']}...")
        service_instance = connect.SmartConnect(host=esxi_cfg['host'], user=esxi_cfg['user'], pwd=esxi_cfg['password'], sslContext=ssl._create_unverified_context())
        # ... (остальной код без изменений)
        content = service_instance.RetrieveContent()
        vm = find_vm_by_name(content, args.vm_name)
        if not vm:
            raise RuntimeError(f"Виртуальная машина '{args.vm_name}' не найдена.")
        
        print(f"Найдена ВМ: {vm.name}. Запрос аренды на экспорт...")
        lease = vm.ExportVm()

        while lease.state == vim.HttpNfcLease.State.initializing:
            time.sleep(1)
        if lease.state != vim.HttpNfcLease.State.ready:
            raise RuntimeError(f"Ошибка получения аренды: {lease.error.msg if lease.error else 'Неизвестное состояние'}")
        
        print("Аренда получена. Скачивание файлов ВМ...")
        os.makedirs(vm_backup_path, exist_ok=True)

        session = requests.Session()
        session.headers.update({"Cookie": service_instance._stub.cookie})
        
        files_to_download = []
        for device in lease.info.deviceUrl:
            file_name = os.path.basename(urlparse(device.url).path)
            corrected_url = device.url.replace('*/', f"{esxi_cfg['host']}/", 1)
            head_response = session.head(corrected_url, verify=False)
            file_size = int(head_response.headers.get('Content-Length', 0))
            files_to_download.append({'name': file_name, 'url': corrected_url, 'size': file_size})

        print("Начинаем скачивание файлов...")
        for file_info in files_to_download:
            local_path = os.path.join(vm_backup_path, file_info['name'])
            download_file_with_progress(local_path, file_info['url'], session, file_info['size'])

        print("\nВсе файлы ВМ успешно скачаны локально.")

        if args.destination == 'cloud':
            print("Начинается процесс загрузки в облако...")
            archive_name = shutil.make_archive(vm_backup_path, 'gztar', vm_backup_path)
            print(f"Создан архив: {archive_name}")
            
            upload_to_nextcloud(archive_name, config['nextcloud'])
            
            print("Очистка временных файлов...")
            os.remove(archive_name)
            shutil.rmtree(vm_backup_path)
            
        elif args.destination == 'file':
            print(f"Бэкап успешно сохранен в локальной папке: {vm_backup_path}")

    except Exception as e:
        print(f"\nПроизошла критическая ошибка: {e}")
    finally:
        if lease:
            lease.HttpNfcLeaseComplete()
        if service_instance:
            connect.Disconnect(service_instance)

if __name__ == "__main__":
    main()
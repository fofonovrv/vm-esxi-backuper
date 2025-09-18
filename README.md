
# VM ESXi Backuper

A simple and powerful script for creating full backups of virtual machines from a standalone **VMware ESXi** host. The script uses the official vSphere API (HTTP NFC Lease) and does not require SSH to be enabled on the host.

## 🚀 Key Features

  * **SSH-Free Operation:** All interaction with ESXi is handled securely through the vSphere API (port 443).
  * **Full Backups:** Creates a complete image of a virtual machine, including all its disks and configuration files (`.vmdk`, `.vmx`, etc.).
  * **Dual Destinations:**
    1.  **`file`**: Saves the backup to a local directory.
    2.  **`cloud`**: Automatically archives the backup into a `.tar.gz` file and uploads it to a **Nextcloud** instance via the WebDAV protocol.
  * **Centralized Configuration:** All settings (credentials, paths) are managed in a single `config.yaml` file.
  * **Informative Output:** Displays progress bars for file downloads.

## 📋 Prerequisites

  * Python 3.8 or newer.
  * Access to an ESXi host (versions 6.7, 7.0, 8.0) with a license that does not block API access.
  * (Optional) A Nextcloud account with WebDAV access for cloud uploads.

## ⚙️ Installation and Setup

### 1\. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/vm-esxi-backuper.git
cd vm-esxi-backuper
```

### 2\. Create and Activate a Virtual Environment

Using a virtual environment is highly recommended to keep dependencies isolated.

```bash
# Create the environment (e.g., using uv)
uv venv

# Activate the environment
# For Linux / macOS:
source .venv/bin/activate
# For Windows (PowerShell):
# .\.venv\Scripts\Activate.ps1
```

### 3\. Install Dependencies

All required libraries are listed in the `requirements.txt` file.

```bash
uv pip install -r requirements.txt
```

### 4\. Configure the Script

The script uses a `config.yaml` file for all its settings.

1.  Create a copy of the example configuration file:
    ```bash
    cp config.yaml.example config.yaml
    ```
2.  Open `config.yaml` in a text editor and fill in your details.

**Example `config.yaml`:**

```yaml
# ESXi Host Connection Settings
esxi:
  host: 10.1.21.1
  user: root
  password: "YourSecretEsxiPassword"

# Backup Storage Settings
storage:
  # Local directory for storing backups (destination: file)
  # or for temporary files before uploading to the cloud.
  local_backup_dir: /home/user/backups/

# Nextcloud Connection Settings
nextcloud:
  # WebDAV URL for your Nextcloud instance (found in Nextcloud's file settings)
  url: https://your.nextcloud.com/remote.php/dav/files/USERNAME
  user: backup_user
  password: "YourSecretNextcloudPassword"
  # Directory on the Nextcloud server to store backups
  remote_dir: /backups/
```

## 🚀 Usage

Run the script from the command line, specifying the configuration file, the VM name, and the destination.

### Example 1: Saving a backup to a local directory

```bash
python3 backup_vm.py --config config.yaml --vm-name "My-Web-Server" --destination file
```

> The backup will be saved to the directory specified in `local_backup_dir` in your `config.yaml` file.

### Example 2: Saving a backup to Nextcloud

```bash
python3 backup_vm.py --config config.yaml --vm-name "My-Database-VM" --destination cloud
```

> The script will first download the VM files to a temporary local folder, create a `.tar.gz` archive, upload it to Nextcloud, and then clean up the temporary files from the local disk.

### Getting Help

```bash
python3 backup_vm.py --help
```

## 📦 `requirements.txt` File

The contents of the dependency file:

```text
pyvmomi
pyyaml
webdavclient3
requests
tqdm
```

## 📜 License

This project is distributed under the MIT License. See the `LICENSE` file for more details.
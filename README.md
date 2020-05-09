# tg

Console telegram client.

(!) currently in development

More documentation and plans for this project at [wiki](https://github.com/paul-nameless/tg/wiki)


## Requirements

- [tdlib](https://tdlib.github.io/td/build.html?language=Python)
  For macOS:
  ```sh
  brew install tdlib
  ```
- `python3.8`
- `pip3 install python-telegram`
- config file at `~/.config/tg/tg.conf`
  ```ini
  [DEFAULT]
  api_id = [api id]
  api_hash = [api hash]
  phone = [phone]
  enc_key = [random key for encrypting your database]
  notify_cmd = /usr/local/bin/terminal-notifier -title "{title}" -subtitle "{subtitle}" -message "{msg}" -appIcon "{icon_path}" -sound default
  ```
  Where:
    - `app_id` and `api_hash` is keys from [telegram](https://core.telegram.org/api/obtaining_api_id)
    - `phone` your phone number (or login)
    - `notify_cmd` can be any executable

## Usage

Clone repository and run it

```sh
git clone git@github.com:paul-nameless/tg.git
cd tg
PYTHONPATH=. python3 tg/main.py
```

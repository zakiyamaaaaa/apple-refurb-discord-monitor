# Apple整備済MacBook Discord通知

Apple日本の認定整備済製品ページをGitHub Actionsで定期チェックし、前回の一覧になかったMacBook系商品だけをDiscord Webhookへ通知します。

監視対象の初期URL:

https://www.apple.com/jp/shop/refurbished/mac/macbook-air-macbook-pro

## GitHub Actionsで動かす

このリポジトリは `.github/workflows/apple-refurb-monitor.yml` で1時間おきに監視します。毎時17分ごろに実行されます。

1. GitHubリポジトリの `Settings` -> `Secrets and variables` -> `Actions` を開きます。
2. `New repository secret` で `DISCORD_WEBHOOK_URL` を追加します。
3. 値にはDiscordのWebhook URLを入れます。
4. `Actions` タブから `Apple Refurb Monitor` を手動実行するか、1時間おきの自動実行を待ちます。

初回実行では通知せず、`data/apple_refurb_state.json` に現在の一覧を保存して基準にします。2回目以降、前回なかった商品だけDiscordに通知します。

ワークフロー内では `APPLE_REFURB_FILTER` を `MacBook (Air|Pro)` にしているため、MacBook AirとMacBook Proだけを通知対象にします。MacBookを含む全商品に広げたい場合は、workflowの環境変数を `MacBook` に変えてください。

## ローカルで試す

Discordで通知したいチャンネルの「連携サービス」からWebhook URLを作り、次のように環境変数へ入れます。

```bash
cd /Users/shoichiyamazaki/development/apple-refurb-discord-monitor
export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'
```

Webhookの疎通確認:

```bash
python3 apple_refurb_watch.py --test-webhook
```

初回の基準保存:

```bash
python3 apple_refurb_watch.py --seed
```

通常チェック:

```bash
python3 apple_refurb_watch.py
```

初回から現在出ている商品を全部通知したい場合だけ、次を使います。

```bash
python3 apple_refurb_watch.py --notify-existing
```

## Macで5分ごとに動かす場合

状態ファイル用ディレクトリを作ります。

```bash
mkdir -p "$HOME/Library/Application Support/apple-refurb-monitor"
```

テンプレートをLaunchAgentsへコピーします。

```bash
cp apple_refurb_monitor.plist.template "$HOME/Library/LaunchAgents/com.local.apple-refurb-discord.plist"
```

コピーしたplist内の `PASTE_DISCORD_WEBHOOK_URL_HERE` を実際のDiscord Webhook URLに置き換えます。Webhook URLは秘密情報なので、権限も絞ってください。

```bash
chmod 600 "$HOME/Library/LaunchAgents/com.local.apple-refurb-discord.plist"
```

登録してすぐ実行します。

```bash
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.local.apple-refurb-discord.plist"
launchctl enable "gui/$(id -u)/com.local.apple-refurb-discord"
launchctl kickstart -k "gui/$(id -u)/com.local.apple-refurb-discord"
```

止める場合:

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.local.apple-refurb-discord.plist"
```

ログ:

```bash
tail -f "$HOME/Library/Logs/apple-refurb-discord.out.log"
tail -f "$HOME/Library/Logs/apple-refurb-discord.err.log"
```

## 調整

チェック間隔は `apple_refurb_monitor.plist.template` の `StartInterval` で変更できます。現在は300秒です。

商品名フィルタは正規表現です。初期値は `MacBook` です。Actionsでは `MacBook (Air|Pro)` を指定しています。

```bash
APPLE_REFURB_FILTER='MacBook Pro' python3 apple_refurb_watch.py
```

## 注意

初回の通常実行では通知せず、現在の一覧を基準として保存します。これは既存商品を大量通知しないためです。以後、前回チェック時に存在しなかったMacBook系商品が出たときだけ通知します。

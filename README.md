# Apple整備済Mac mini Discord通知

Apple日本の認定整備済製品（Macカテゴリ）をGitHub Actionsで定期チェックし、前回の一覧になかった **Mac mini** だけをDiscord Webhookへ通知します。

監視対象URL:

https://www.apple.com/jp/shop/refurbished/mac/mac-mini

商品名フィルタは正規表現 `Mac mini` です。MacカテゴリのHTMLにはMacBookなど他製品も含まれるため、フィルタでMac miniに限定しています。

**注意:** 整備済Mac miniがApple日本で一度も掲載されていない時期は、一覧が0件のままです。その間は通知は出ませんが、新規掲載が始まったタイミングでDiscordに通知されます。

## GitHub Actionsで動かす

このリポジトリは `.github/workflows/apple-refurb-monitor.yml` で1時間おきに監視します。毎時17分ごろに実行されます。

1. GitHubリポジトリの `Settings` -> `Secrets and variables` -> `Actions` を開きます。
2. `New repository secret` で `DISCORD_WEBHOOK_URL` を追加します。
3. 値にはDiscordのWebhook URLを入れます。
4. `Actions` タブから `Apple Refurb Monitor` を手動実行するか、1時間おきの自動実行を待ちます。

state ファイル `data/apple_refurb_state.json` がある場合、前回と比較して **新しく載った Mac mini** だけ通知します。初回に state が無い通常実行では、現在の一覧を基準として保存し通知しません。

### 別デバイスに変えたい場合

`APPLE_REFURB_URL` / `APPLE_REFURB_FILTER` を変更したら、必ず `python3 apple_refurb_watch.py --seed` で state を作り直し、コミットしてください。古い state のままだと切り替え直後に大量通知されることがあります。

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

フィルタ例:

```bash
APPLE_REFURB_FILTER='Mac mini' python3 apple_refurb_watch.py
```

## 注意

Mac mini 以外の整備済Mac（MacBook、iMac など）が載っていても、フィルタにより通知対象外です。前回チェック時に存在しなかった Mac mini が載ったときだけ通知します。

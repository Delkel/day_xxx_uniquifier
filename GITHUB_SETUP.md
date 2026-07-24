# GitHub setup

## Что заливать

- Репозиторий: `day_xxx_uniquifier`
- Видимость: public
- Release tag: `v1.2.0`
- Release asset: `release/day_xxx_uniquifier_macos_app.zip`
- Manifest file in repo root: `update-manifest.json`

## После создания репозитория

1. Репозиторий настроен под `Delkel/day_xxx_uniquifier`; если он будет другим, замени owner/repo в `update-manifest.json`.
2. Репозиторий настроен под `Delkel/day_xxx_uniquifier`; если он будет другим, замени `updateManifestUrl` в `app/settings.json` на raw-ссылку:

```json
{
  "updateManifestUrl": "https://raw.githubusercontent.com/Delkel/day_xxx_uniquifier/main/update-manifest.json"
}
```

3. Пересобери zip из папки `app`.
4. Загрузи новый zip в GitHub Release `v1.2.0`.

## Команды, если установлен GitHub CLI

```sh
gh repo create day_xxx_uniquifier --public --source=. --remote=origin --push
gh release create v1.2.0 release/day_xxx_uniquifier_macos_app.zip --title "v1.2.0" --notes "Mac auto-updater build"
```

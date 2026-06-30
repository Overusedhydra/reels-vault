---
tags: [vault-index]
---

# Reel Vault

Your extracted reels live in topic folders. Each reel is auto-tagged with creator, niche, and category.

## Browse by Topic

Topics are created automatically when you save reels. Just add `--topic <name>` when extracting.

## Browse by Creator

Extracted reels link back to their creator. Search for `creator:` in your vault.

## All Reels

```dataview
TABLE creator AS "Creator", topic AS "Topic", extracted AS "Date"
FROM ""
WHERE source
SORT extracted DESC
```

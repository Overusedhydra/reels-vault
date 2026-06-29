---
aliases: [Reel Transcripts, Raw Extracts]
tags: [extracts, index]
created: 2026-06-29
---

# Extracts

Raw transcripts and analysis from extracted reels. Each extract is tagged by topic and creator for cross-referencing.

## How Extracts Work

1. You paste a reel URL
2. I extract transcript + analyze
3. Say "drop it" → it lands here
4. Tagged with topics + creator
5. Key frameworks filed in [[topics/]]
6. Recipes added to [[Recipe Book]]

## All Extracts

```dataview
TABLE creator AS "Creator", file.tags AS "Topics", file.cday AS "Added"
FROM "extracts"
WHERE file.name != "Extracts"
SORT file.cday DESC
```

## Filter by Creator

```dataview
TABLE file.tags AS "Topics", file.cday AS "Added"
FROM "extracts"
WHERE creator = "Alex Hormozi"
SORT file.cday DESC
```

```dataview
TABLE file.tags AS "Topics", file.cday AS "Added"
FROM "extracts"
WHERE creator = "Gary Vaynerchuk"
SORT file.cday DESC
```

```dataview
TABLE file.tags AS "Topics", file.cday AS "Added"
FROM "extracts"
WHERE creator = "Ali Abdaal"
SORT file.cday DESC
```

## Filter by Topic

```dataview
TABLE creator AS "Creator", file.cday AS "Added"
FROM "extracts"
WHERE contains(tags, "hooks")
SORT file.cday DESC
```

```dataview
TABLE creator AS "Creator", file.cday AS "Added"
FROM "extracts"
WHERE contains(tags, "ads")
SORT file.cday DESC
```

```dataview
TABLE creator AS "Creator", file.cday AS "Added"
FROM "extracts"
WHERE contains(tags, "youtube")
SORT file.cday DESC
```

---
aliases: [Creator Directory, Creators]
tags: [creators, index]
created: 2026-06-29
---

# Creator Profiles

Every creator in one place. Click any name to see everything they've taught across all topics.

## All Creators

```dataview
TABLE niche AS "Niche", key_lesson AS "Key Lesson", extract_count AS "Extracts"
FROM "content-recipes/creators"
WHERE file.name != "Creator Template"
SORT file.name ASC
```

## By Category

### Content & Creator Economy
- [[Alex Hormozi]] — Ads, scaling, volume
- [[Gary Vaynerchuk]] — Social media, brand
- [[Ali Abdaal]] — YouTube, productivity
- [[Iman Gadzhi]] — Agency, education

### Marketing & Business
- *(add as you extract)*

### AI & Tech
- *(add as you extract)*

## How Creator Profiles Work

Each creator profile shows:
- **Overview** — Who they are, what they're known for
- **Key frameworks** — Their signature systems
- **Contributions by topic** — What they've taught about hooks, scripting, etc.
- **All extracts** — Every reel/video extracted from them
- **Related recipes** — Formulas they've contributed to

## Adding a New Creator

When you paste a reel from someone new:
1. Extract runs → transcript + analysis
2. Say "drop it"
3. I create their profile (or update existing)
4. Frameworks filed under [[topics/]]
5. Recipes added to [[Recipe Book]]

```dataview
LIST
FROM "content-recipes/creators"
WHERE file.name != "Creator Template"
SORT file.name ASC
```

---
aliases: [Content Recipes, Knowledge Base, Playbook]
tags: [moc, index, content-recipes]
created: 2026-06-29
---

# Content Recipes

A cross-referenced knowledge base built from top creators. Every insight is organized by **topic** (what it's about) and **creator** (who said it). Filter however you want.

## How It Works

1. **Paste a reel URL** → I extract transcript + analyze
2. **Say "drop it"** → It lands here, tagged by topic and creator
3. **Browse by topic** → See what every creator says about hooks, scripting, etc.
4. **Browse by creator** → See everything a specific creator teaches
5. **Copy-paste recipes** → Ready-to-use formulas from anyone

## Browse by Topic

| Topic | What's Inside |
|-------|---------------|
| [[Hooks & Openings]] | First 3 seconds, pattern interrupts, curiosity gaps |
| [[Scripting & Storytelling]] | Narrative structures, frameworks, writing formulas |
| [[Editing & Production]] | Pacing, transitions, visual effects, format specs |
| [[Thumbnails & Visuals]] | Click-through optimization, design principles |
| [[Copywriting & Ads]] | Ad copy, landing pages, email sequences |
| [[YouTube Strategy]] | Titles, retention, algorithm, channel growth |
| [[Short-Form Video]] | Reels, TikTok, Shorts — platform-specific tactics |
| [[Content Frameworks & Systems]] | Repeatable systems, workflows, scaling content |
| [[Distribution & Growth]] | Posting strategy, cross-platform, audience building |
| [[AI & Tools]] | AI workflows, automation, content tools |
| [[Marketing & Strategy]] | Positioning, funnels, brand building |

## Browse by Creator

```dataview
TABLE niche AS "Niche", key_lesson AS "Key Lesson"
FROM "creators"
WHERE file.name != "Creator Template"
SORT file.name ASC
```

## Browse by Extract

```dataview
TABLE creator AS "Creator", length(transcript) AS "Words", file.cday AS "Added"
FROM "extracts"
WHERE file.name != "Extracts"
SORT file.cday DESC
```

## Quick Links

- [[Recipe Book]] — Copy-paste formulas from any creator
- [[Creator Profiles]] — All creators, one place
- [[Extracts]] — Raw transcripts

## Recently Added

```dataview
TABLE creator AS "Creator", file.cday AS "Added"
FROM "extracts"
WHERE file.name != "Extracts"
SORT file.cday DESC
LIMIT 10
```

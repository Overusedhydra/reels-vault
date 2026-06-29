---
aliases: [Recipes, Playbooks, Formulas, Copy-paste]
tags: [recipes, playbooks]
created: 2026-06-29
---

# Recipe Book

Ready-to-use formulas from top creators. Copy, paste, customize, ship.

## Filter by Creator

```dataview
LIST
FROM "recipes"
WHERE file.name != "Recipe Book"
SORT file.name ASC
```

## All Recipes by Category

```dataview
TABLE tags AS "Tags"
FROM "recipes"
WHERE file.name != "Recipe Book"
SORT file.name ASC
```

---

## Hook Recipes

### Recipe: The Controversial Take
```
[Popular belief] is wrong. Here's why.
```
**Example:** "Morning routines are overrated. Here's why."
**Source:** [[Hormozi]], [[GaryVee]]

### Recipe: The Specific Number
```
[Number] [things/steps/ways] to [desirable outcome]
```
**Example:** "7 ways to double your content output this week"
**Source:** [[Hormozi]], [[Ali Abdaal]]

### Recipe: The Time Proof
```
I [did X] for [time period]. Here's what happened.
```
**Example:** "I posted 3x/day for 90 days. Here's what happened."
**Source:** [[Ali Abdaal]], [[Iman Gadzhi]]

### Recipe: The Stop Scrolling
```
Stop scrolling. [Bold claim about what you're about to show].
```
**Example:** "Stop scrolling. This one hack saved me 20 hours last week."
**Source:** Short-form best practice

---

## Script Recipes

### Recipe: Hormozi's Ad Framework
```
Hook (3-5 seconds)
Meat (30-60 seconds) — educate on offer/problem/solution
CTA (5-10 seconds) — tell them exactly what to do
```
**Best for:** Ads, Reels, any conversion-focused content
**Source:** [[Hormozi]]

### Recipe: The Story Arc
```
Setup (who, what, where)
Conflict (problem, obstacle, tension)
Resolution (how it was solved)
Lesson (what we learned)
```
**Best for:** YouTube, storytelling content
**Source:** General storytelling, [[GaryVee]]

### Recipe: The Listicle
```
Hook: "X things you didn't know about [topic]"
Item 1: [Most surprising]
Item 2: [Most useful]
Item 3: [Most actionable]
Wrap-up: Summary + CTA
```
**Best for:** Shorts, Reels, quick educational content
**Source:** Short-form best practice

---

## CTA Recipes

### Recipe: The Comment CTA
```
Comment [specific word] if you want [desired outcome]
```
**Example:** "Comment 'MAP' if you want a free $100M scaling roadmap"
**Source:** [[Hormozi]]

### Recipe: The Save CTA
```
Save this for later — you'll need it when [scenario]
```
**Example:** "Save this for later — you'll need it when you launch your next ad"
**Source:** Instagram best practice

### Recipe: The Share CTA
```
Send this to someone who [needs this / is struggling with X]
```
**Example:** "Send this to someone who's stuck on content ideas"
**Source:** Growth hack

---

## Thumbnail Recipes

### Recipe: The React Thumbnail
```
Expressive face (surprise/concern) + 3-5 word text + relevant object
```
**Example:** 😮 face + "THIS CHANGED EVERYTHING" + product image
**Source:** YouTube best practice

### Recipe: The Before/After
```
Split screen: Before (bad) | After (good)
```
**Example:** Messy desk → organized desk
**Source:** Transformation content

---

## Ad Recipes

### Recipe: The Problem-Agitate-Solution Ad
```
Hook: "Are you struggling with [pain point]?"
Agitate: "It's getting worse because [reason]. [Real consequences]."
Solution: "Here's what [product] does: [3 benefits]."
CTA: "[Specific action] today and [outcome]."
```
**Best for:** Facebook/Meta ads, cold traffic
**Source:** [[Hormozi]], direct response

### Recipe: The Testimonial Ad
```
Hook: "[Result] in [timeframe]."
Proof: "Here's what [customer] said: [testimonial]"
Mechanism: "Here's how it works: [1-2 sentences]"
CTA: "[Action] to get the same result."
```
**Best for:** Warm audiences, retargeting
**Source:** [[Hormozi]]

---

*Add new recipes as you extract them from creators*

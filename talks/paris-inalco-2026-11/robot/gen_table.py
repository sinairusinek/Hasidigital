"""Generate the 'five points of view around one book' engraving for the Paris INALCO talk.

Same house style as m1_press_engraving.png: 19th-century wood engraving, black ink
cross-hatching on warm cream paper. NO text is asked of the model (it renders text
badly -- see the garbled STORY/INDEX cards in m1_press_engraving.png); the character
names are overlaid as vector text in table_slide.html instead.
"""
import os, sys, json
from google import genai

for line in open('/Users/sinairusinek/Documents/GitHub/Hasidigital/.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
MODEL = 'gemini-2.5-flash-image'
HERE = os.path.dirname(os.path.abspath(__file__))

STYLE = (
    "Style: a 19th-century wood-engraving book plate, black ink cross-hatching and fine parallel line work "
    "on plain warm cream paper, slight sepia tone, like an illustration in an old book of learned societies. "
    "No colour wash, no modern shading, no photographic realism. Respectful and witty, gently humorous, "
    "never caricature or mockery of any religion or people. "
    "ABSOLUTELY NO LETTERS, WORDS, NUMBERS, TITLES, LABELS, CAPTIONS OR SIGNATURES ANYWHERE IN THE IMAGE. "
    "Book spines, pages, scrolls and charts must be blank or show only abstract squiggles and ruled lines, "
    "never readable writing. Generous cream margins around the whole scene."
)

SCENE = (
    "A wide horizontal scene: five scholars seated around one large round table, seen from a slightly raised "
    "three-quarter angle so every figure is visible and none has their back fully to us. In the exact centre of "
    "the table lies ONE large open book, much bigger than a normal book, lit as the focus of the picture; all five "
    "scholars lean in and examine that same open book with evident concentration. Each scholar is a distinct person "
    "with a different posture, age, build and dress, and each is surrounded by the props of their own discipline, "
    "so that their point of view is legible from their appearance and their belongings alone. "
    "Above each scholar's head floats a thought bubble, drawn in the same engraved line style, containing a small "
    "wordless pictorial emblem of how that scholar sees the book. "
)

FIGURES = (
    "Going clockwise around the table: "
    "(1) HEBREW LITERARY HISTORY: an elderly bearded scholar in a dark frock coat with small round spectacles, "
    "a stack of large worn folio volumes with ornate blank spines and ribbon bookmarks at his elbow, holding a "
    "magnifying glass over the page; his thought bubble shows a chain of small books linked one to the next in a "
    "line, like a genealogy or a timeline of editions. "
    "(2) COMPARATIVE FOLKLORE: a traveller-scholar in a rough field coat with a satchel and a walking staff, "
    "a card index drawer of small filing cards open in front of them and a rolled map; their thought bubble shows "
    "a world globe with several identical little story-motif symbols scattered across different continents and "
    "faint lines connecting them. "
    "(3) NARRATOLOGICAL THEORY: a sharp modern-looking theorist in a plain turtleneck, surrounded by diagrams; "
    "they hold a pair of dividers or compasses over the page as if measuring it; their thought bubble shows the "
    "story reduced to an abstract diagram: a row of empty boxes joined by arrows, and a branching tree structure. "
    "(4) THEOLOGY AND HISTORY OF RELIGION: a scholar in dark clerical-academic robes with a skullcap, flanked by "
    "a tall heavy clasped tome on a small lectern and a candle; their hands are raised slightly as if in exposition; "
    "their thought bubble shows rays of light descending from a cloud onto a small open book, and a ladder rising. "
    "(5) ECONOMIC HISTORY: a brisk scholar in a waistcoat with shirtsleeves rolled, an abacus and stacks of coins "
    "and a ledger beside them, a rolled graph under one hand; their thought bubble shows a rising line graph, a "
    "set of scales, and small coins and a merchant's cart. "
)

PROMPTS = {
    't1': SCENE + FIGURES + STYLE,
    't2': SCENE + FIGURES +
          "Compose it as a wide panoramic plate, the table seen more from the side so the five scholars are spread "
          "across the width of the image in a shallow arc, with the open book large and central and the five thought "
          "bubbles clearly separated along the top. " + STYLE,
    't3': SCENE + FIGURES +
          "Make the thought bubbles large and prominent, occupying the upper third of the plate, each clearly "
          "attached by a trail of small circles to its own scholar, so the five different ways of seeing are the "
          "most striking thing in the picture. " + STYLE,
}

which = sys.argv[1:] or list(PROMPTS)
log = []
for name in which:
    r = client.models.generate_content(model=MODEL, contents=PROMPTS[name])
    u = r.usage_metadata
    saved = False
    for part in r.candidates[0].content.parts:
        if getattr(part, 'inline_data', None) and part.inline_data.data:
            open(os.path.join(HERE, name + '.png'), 'wb').write(part.inline_data.data)
            saved = True
    rec = dict(name=name, saved=saved, prompt_tokens=u.prompt_token_count,
               output_tokens=u.candidates_token_count, total=u.total_token_count)
    print(json.dumps(rec))
    log.append(rec)
json.dump(log, open(os.path.join(HERE, 'usage_table.json'), 'w'), indent=1)

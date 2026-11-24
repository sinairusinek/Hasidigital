import os, sys, json
from google import genai
from google.genai import types

for line in open('/Users/sinairusinek/Documents/GitHub/Hasidigital/.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
MODEL = 'gemini-2.5-flash-image'
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, 'm1_press_engraving.png'), 'rb').read()

BASE = ("Edit this wood-engraving. Keep the printing press, the gears, the steam, the paper strip going in on the left, "
        "the flapping black coat tails and the curly side-locks exactly as they are, in the same black-ink engraving style on cream paper. "
        "Change two things. "
        "1) The hat: make it a proper Hasidic shtreimel: a WIDE, LOW, flat ring of dark brown fur, much wider than it is tall, "
        "around a small round black velvet crown in the middle. Not a bowler, not a cylinder. "
        "2) Replace the three small cards flying out on the right with five separate printed book pages (or page fragments) flying out in a stream, "
        "each showing ONE distinct element of a printed book's apparatus, recognisable by its layout: "
        "(a) a running head: a page whose top line is a short centred header above a ruled line, with text below; "
        "(b) a catchword: a page with text and, alone at the very bottom corner under the last line, a single isolated word; "
        "(c) a chapter opening: a page with an ornamental engraved headpiece band and a large decorated initial; "
        "(d) a table of contents: rows of entries joined by dotted leader lines to page numbers on the far side; "
        "(e) an index: a page in two narrow columns of short entries, each followed by numbers. ")
VARIANTS = {
  'e1': BASE + "Show the text on the pages only as fine engraved lines and dots, with no legible words or letters, so the layout alone identifies each element.",
  'e2': BASE + "Show the text on the pages only as fine engraved lines and dots, with no legible words or letters. Make the five pages larger and spread in a gentle arc, so each layout is clearly readable at slide size.",
  'e3': BASE + "Text on the pages is fine engraved lines, except that each page carries one small clear printed label in capitals, spelled exactly: "
        "RUNNING HEAD, CATCHWORD, CHAPTER, CONTENTS, INDEX. No other words anywhere.",
}
for name in (sys.argv[1:] or list(VARIANTS)):
    r = client.models.generate_content(model=MODEL, contents=[types.Part.from_bytes(data=src, mime_type='image/png'), VARIANTS[name]])
    u = r.usage_metadata; saved = False
    for part in r.candidates[0].content.parts:
        if getattr(part, 'inline_data', None) and part.inline_data.data:
            open(os.path.join(HERE, f'm1_{name}.png'), 'wb').write(part.inline_data.data); saved = True
    print(json.dumps(dict(name=name, saved=saved, prompt_tokens=u.prompt_token_count, output_tokens=u.candidates_token_count, total=u.total_token_count)))

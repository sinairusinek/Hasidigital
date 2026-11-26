"""Final corrections to the personas plate (tbl_k1.png -> m*.png).

  1. Prof. Ketav (far left): restore the EARLIER emblem from f2.png -- three open
     books stepping down, linked by little arrows, a line of descent between
     editions -- in place of the flat row of closed boxes, which reads as a
     flowchart rather than a filiation.
  2. The OLDER woman (second from left) becomes Prof. Fabula, narratological
     theory, and takes the emblem now in the middle bubble (row of boxes joined
     by arrows above a branching tree). The globe leaves her bubble.
  3. The YOUNGER woman (centre) is no longer comparative folklore: she becomes a
     gender studies scholar and gets an emblem of her own.

Only the three leftmost bubbles change. The two men on the right and their
bubbles, all five figures, and the Hebrew book stay exactly as they are.
"""
import os, sys, json
from google import genai
from google.genai import types

for line in open('/Users/sinairusinek/Documents/GitHub/Hasidigital/.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, 'tbl_k1.png'), 'rb').read()

KEEP = ("Edit this wood-engraving. Keep ALL FIVE people exactly as they are: their faces, hair, spectacles, "
        "clothing, hands and poses must not change at all. Keep the big open Hebrew book at the centre of the "
        "table with its dense square Hebrew type, and keep the table and every object on it: the stacks of "
        "folio volumes, the candle, the scrolls, the card index, the quill and the abacus. Keep the same "
        "19th-century black-ink wood-engraving style on warm cream paper, and keep all five thought bubbles in "
        "their present positions and sizes, each with its trail of little circles. ")

BUBBLES = (
    "Change the contents of the THREE LEFTMOST thought bubbles only. "
    "FIRST BUBBLE, above the old bearded man with the magnifying glass at the far left: remove the row of five "
    "identical square boxes joined by arrows. In its place draw THREE SMALL OPEN BOOKS arranged in a descending "
    "diagonal step, one above the next, each joined to the following one by a short curved arrow, so it reads as "
    "a line of descent from one edition of a book to the next. Draw them as little open books with visible pages, "
    "not as closed boxes or rectangles. "
    "SECOND BUBBLE, above the grey-haired woman in the blazer: remove the globe entirely. In its place draw an "
    "abstract story diagram: a single row of five empty rectangles joined left to right by arrows, with a small "
    "branching tree directly beneath the row. "
    "THIRD BUBBLE, above the dark-haired woman in spectacles at the centre: remove whatever is in it now. In its "
    "place draw an emblem of gender: two small human figures side by side, one in a long skirt and one in a coat, "
    "drawn simply as engraved outline figures, with a pair of old-fashioned balance scales above and between them "
    "whose two pans hang at clearly UNEQUAL heights, one pan low and one pan high. "
    "The FOURTH bubble (rays from a cloud onto a book, with a ladder) and the FIFTH bubble (rising graph, scales "
    "and coins) must stay exactly as they are. ")

NOTEXT = ("No letters, words, numbers, labels or captions anywhere in the image, and none inside any bubble. The "
          "only writing in the picture is the Hebrew already printed on the open book's pages, which must stay "
          "unchanged.")

V = {
 'm1': KEEP + BUBBLES + NOTEXT,
 'm2': KEEP + BUBBLES + "Draw the three changed emblems large and clean, filling their bubbles, with simple bold "
       "engraved lines so each is legible at a glance when projected. " + NOTEXT,
}
for name in (sys.argv[1:] or list(V)):
    r = client.models.generate_content(model='gemini-2.5-flash-image',
                                       contents=[types.Part.from_bytes(data=src, mime_type='image/png'), V[name]])
    u = r.usage_metadata; ok = False
    for p in r.candidates[0].content.parts:
        if getattr(p, 'inline_data', None) and p.inline_data.data:
            open(os.path.join(HERE, f'tbl_{name}.png'), 'wb').write(p.inline_data.data); ok = True
    print(json.dumps(dict(name=name, saved=ok, prompt_tokens=u.prompt_token_count,
                          output_tokens=u.candidates_token_count)))

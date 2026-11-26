"""Third pass: g2 has the right people and the right book, but its thought bubbles
drifted -- the chain-of-editions and the globe were lost, and the diagram and the
rays-from-a-cloud ended up on the wrong heads. Restore the five emblems in order,
left to right, without touching the figures or the book."""
import os, sys, json
from google import genai
from google.genai import types

for line in open('/Users/sinairusinek/Documents/GitHub/Hasidigital/.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else 'g2.png'), 'rb').read()

P = ("Edit this wood-engraving. Keep EVERY figure exactly as drawn: the old bearded man with the magnifying glass, "
     "the grey-haired woman in the blazer holding the rolled map, the dark-haired woman in spectacles and a dark "
     "jacket holding the dividers at the centre, the bearded man in the skullcap and tweed, and the man in the "
     "waistcoat on the right. Keep their faces, clothes, hands and poses unchanged. Keep the big open Hebrew book "
     "at the centre of the table with its dense square Hebrew type, and keep the candle, the scrolls, the stacks "
     "of books, the card index, the quill and the abacus. Keep the same 19th-century black-ink wood-engraving "
     "style on warm cream paper. "
     "Change ONLY the five thought bubbles above the five heads. There must be exactly five bubbles, one per "
     "person, each joined to its own head by a trail of small circles, and each must contain this emblem, drawn "
     "as a simple engraved line emblem and NOTHING else. From left to right: "
     "(1) above the old bearded man: a row of five small closed books linked one to the next by short lines, like "
     "a genealogy or a chain of editions; "
     "(2) above the woman with the map: a globe of the earth with the same small identical symbol repeated on "
     "three different continents, joined by faint curved lines; "
     "(3) above the woman with the dividers: an abstract story diagram, a single row of five empty rectangles "
     "joined left to right by arrows, with a small branching tree beneath it; "
     "(4) above the bearded man in the skullcap: rays of light descending from a cloud onto a small open book, "
     "with a ladder rising from the book towards the cloud; "
     "(5) above the man in the waistcoat: a rising zig-zag line graph with an arrow at its end, a pair of balance "
     "scales, and three small stacked coins. "
     "No letters, words, numbers or captions inside the bubbles or anywhere else in the image, except the Hebrew "
     "print already on the book's pages, which must stay as it is.")

for name in (sys.argv[2:] or ['h1', 'h2']):
    r = client.models.generate_content(model='gemini-2.5-flash-image',
                                       contents=[types.Part.from_bytes(data=src, mime_type='image/png'), P])
    u = r.usage_metadata; ok = False
    for p in r.candidates[0].content.parts:
        if getattr(p, 'inline_data', None) and p.inline_data.data:
            open(os.path.join(HERE, f'{name}.png'), 'wb').write(p.inline_data.data); ok = True
    print(json.dumps(dict(name=name, saved=ok, prompt_tokens=u.prompt_token_count,
                          output_tokens=u.candidates_token_count)))

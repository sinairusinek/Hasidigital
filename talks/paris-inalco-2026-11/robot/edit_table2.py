"""Second revision of the personas plate (f2.png -> g*.png).

Three changes asked for:
  1. the middle three scholars should read as more academic
  2. Fabula (centre, narratology) and one other should be women
  3. the open book in the middle should look like a Hasidic stories edition,
     like the pages shown in the print-machine slide

The real Hasidic edition page (crops/chapter.jpg) is passed in as a second
reference image so the model sees the actual typography: square Hebrew type,
a centred heading, a justified block beneath, reading right to left.
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
plate = open(os.path.join(HERE, 'f2.png'), 'rb').read()
page = open(os.path.join(HERE, 'crops', 'chapter.jpg'), 'rb').read()

KEEP = ("Edit the FIRST image, the wood-engraving of five scholars around a round table. "
        "Keep the whole composition: five scholars in an arc around one big open book, all five leaning in and "
        "examining it, five separate thought bubbles above them joined by trails of little circles, the stacks of "
        "folio volumes, the candle, the scrolls, the ledger and the abacus. "
        "Keep exactly the same 19th-century wood-engraving style: black ink cross-hatching and fine parallel line "
        "work on warm cream paper, slight sepia tone. Keep the five thought bubbles and their contents unchanged: "
        "(1) a chain of linked books, (2) a globe with a repeated motif, (3) boxes joined by arrows above a "
        "branching tree, (4) rays from a cloud onto a book with a ladder, (5) a rising graph with scales and coins. ")

BOOK = ("THE BOOK IN THE MIDDLE. Redraw the large open book at the centre of the table so it is clearly a traditional "
        "Hebrew religious book, a Hasidic stories edition, engraved in the same style. Use the SECOND image as the "
        "reference for how its pages must look. Both open pages are set in dense SQUARE HEBREW LETTERS, in solid "
        "justified blocks of small type that run RIGHT TO LEFT, with a short centred heading line in larger Hebrew "
        "letters at the top of each page and a thin ruled line under the heading. The block of text should be a "
        "single dense column per page, with even margins, like a page of a 19th-century Hebrew book. "
        "The volume is thick, bound in worn dark leather with raised bands and blind-tooled borders on the covers, "
        "its pages yellowed and slightly cockled at the edges. Do NOT draw Latin letters, and do NOT draw the "
        "abstract squiggles that are there now: the page must read, at a glance, as Hebrew print. ")

PEOPLE = ("THE THREE MIDDLE SCHOLARS. Make the three central figures look like modern university academics rather "
          "than Victorian gentlemen or countryfolk, while keeping them in the same engraved style and the same "
          "seats and poses. "
          "The SECOND figure from the left, now a traveller in a cap with a walking staff, becomes a WOMAN in her "
          "fifties, a professor of comparative folklore: short practical greying hair, a plain dark blazer over a "
          "simple blouse, reading glasses pushed up on her head; replace the shepherd's crook entirely with a "
          "rolled map held upright in one hand, and leave the open card-index drawer in front of her. "
          "The THIRD figure, in the centre, now a young person in a pale turtleneck holding dividers, becomes a "
          "WOMAN in her forties, a professor of narratological theory: dark hair gathered back, a well-cut dark "
          "jacket, angular modern spectacles; she still holds the pair of dividers over the open book, and a sheet "
          "of diagrams lies beside her. "
          "The FOURTH figure, the scholar of theology and history of religion, stays a man but becomes a modern "
          "academic: keep his skullcap and his beard, but put him in a tweed jacket with a buttoned waistcoat "
          "instead of the shapeless robe, with the heavy clasped tome and the candle still at his place. "
          "All three should look scholarly, alert and dignified. Keep the old bearded man with the magnifying "
          "glass on the far left and the waistcoated economic historian on the far right exactly as they are. ")

NOTEXT = ("No Latin letters, no words, no numbers, no labels and no captions anywhere in the image. The ONLY "
          "writing anywhere is the Hebrew print on the two open pages of the central book, and on the spines of "
          "the other books, which may show a few small Hebrew letters. Everything else stays blank.")

V = {
 'g1': KEEP + BOOK + PEOPLE + NOTEXT,
 'g2': KEEP + BOOK + PEOPLE +
       "Draw the central open book larger and tilted slightly towards the viewer, so both Hebrew pages are clearly "
       "legible as Hebrew print at a glance and the book is unmistakably the focus of the picture. " + NOTEXT,
}
for name in (sys.argv[1:] or list(V)):
    r = client.models.generate_content(
        model='gemini-2.5-flash-image',
        contents=[types.Part.from_bytes(data=plate, mime_type='image/png'),
                  types.Part.from_bytes(data=page, mime_type='image/jpeg'),
                  V[name]])
    u = r.usage_metadata; ok = False
    for p in r.candidates[0].content.parts:
        if getattr(p, 'inline_data', None) and p.inline_data.data:
            open(os.path.join(HERE, f'{name}.png'), 'wb').write(p.inline_data.data); ok = True
    print(json.dumps(dict(name=name, saved=ok, prompt_tokens=u.prompt_token_count,
                          output_tokens=u.candidates_token_count)))

"""Consumption slide: edit m1_e2.png on the OUTPUT (right) side only.

The slide's argument is not how stories are made but how they are READ: academic
reading is itself a technical endeavour -- categories, analytic vocabularies and
theories are machinery, and they have their own material machines, the index above all.

Three variants to choose between:
  A  same flow, different goods -- the three flying pages become the scholar's
     instruments (card index, classification table, category tree).
  B  a SECOND machine -- the pages fly on into a reading engine with its own crank
     that digests them and emits catalogue cards. States the thesis most plainly.
  C  a reader's DESK -- the apparatus sits as standing equipment, not as output.

Per Sinai: drop the Hasidic signs (shtreimel, side-locks, coat tails) -- on a
consumption slide they belong to the material, not the reader. No institutional
apparatus (tenure/grants/RAs): no engraved object says "grant" without a caption.
LANDSCAPE: the slide is 16:9, so the plate must be a wide horizontal composition.
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
src = open(os.path.join(HERE, 'm1_e2.png'), 'rb').read()

LANDSCAPE = (
    "FORMAT, THIS MATTERS MOST: the output image must be a WIDE PANORAMIC LANDSCAPE PLATE in 16:9 proportions, "
    "about twice as wide as it is tall, for a widescreen slide. It must NOT be square. Lay the scene out along a "
    "long horizontal band: spread the elements apart from far left to far right so they fill the whole width, and "
    "leave only shallow bands of empty cream paper above and below them. Think of a wide frieze or a panoramic "
    "book plate printed across a double page, never a square vignette. ")

KEEP = (
    "Edit this 19th-century wood-engraving. Keep the cast-iron printing press on the LEFT exactly as it is: "
    "its frame, gears, rollers, crank, the big spoked flywheel, the plain sheet of paper feeding in on the left, "
    "and its shadow. Keep exactly the same style throughout: black ink cross-hatching and fine parallel line work "
    "on warm cream paper, slight sepia tone, no colour, no photographic shading. "
    "REMOVE these from the machine, leaving clean engraved metal and empty cream paper in their place: the fur hat "
    "on top, the two curly side-locks hanging beside it, and the large flapping black coat tails behind it. "
    "The machine must read as a plain printing press with no clothing and no human attributes at all. "
    "Reduce the steam cloud at the top right to a small wisp so it does not crowd the right-hand side. ")

NOTEXT = (
    "ABSOLUTELY NO LETTERS, WORDS, NUMBERS, TITLES, LABELS, CAPTIONS OR SIGNATURES ANYWHERE. Printed matter, cards, "
    "pages, drawers and charts carry only fine engraved lines, dots, rules and abstract squiggles, never readable "
    "writing. No human figures, no hands, no faces anywhere in the picture. ")

A = (KEEP +
 "CHANGE THE RIGHT-HAND SIDE. Replace the three flying printed pages with THREE FLYING OBJECTS OF SCHOLARLY "
 "APPARATUS, drawn in the same engraved style, in the same gentle arc, with the same little speed lines, as though "
 "the press were issuing the reader's instruments rather than pages: "
 "(1) a wooden CARD-INDEX DRAWER seen at an angle, open, with a row of upright filing cards standing in it and one "
 "card lifted clear above the others; "
 "(2) a CLASSIFICATION TABLE: a stiff ruled sheet gridded into empty boxes by horizontal and vertical rules, like a "
 "blank taxonomic chart; "
 "(3) a TREE OF CATEGORIES: a sheet bearing a branching diagram, one small circle at the top dividing by ruled lines "
 "into two, then four, then eight small circles below. "
 "Keep them large and clearly separated so each is legible at slide size. " + NOTEXT + LANDSCAPE)

B = (KEEP +
 "CHANGE THE RIGHT-HAND SIDE. The three printed pages still fly out of the press, but now they fly ONWARD INTO A "
 "SECOND MACHINE standing to the RIGHT of the press, so the picture reads left to right as one continuous line: "
 "press -> flying pages -> second machine -> its own product. "
 "THE SECOND MACHINE is a READING ENGINE, drawn in the same engraved style and the same cast-iron idiom as the press "
 "but visibly different and somewhat smaller: a squat cabinet of wood and iron with a hopper or slot on its left "
 "side into which the flying pages are being drawn, a bank of toothed gears and a small crank handle on its flank, "
 "and a tall rack of narrow CARD-INDEX DRAWERS built into its body, one drawer pulled open with upright filing cards "
 "standing in it. From a slot on the RIGHT of this second machine a neat stream of small CATALOGUE CARDS issues in a "
 "line, each card ruled with a few engraved lines, flying off to the right with little speed lines. "
 "Above the second machine, one small branching TREE DIAGRAM of circles joined by ruled lines is engraved as if "
 "stencilled on a plate fixed to its casing. The two machines must sit on the same ground line, as a matched pair. "
 + NOTEXT + LANDSCAPE)

C = (KEEP +
 "CHANGE THE RIGHT-HAND SIDE ONLY. THE PRINTING PRESS MUST REMAIN IN THE PICTURE, drawn in full on the LEFT "
 "HALF of the plate, unchanged, with its sheet of paper feeding in -- do not remove it, do not crop it, do not "
 "replace it. The plate shows TWO THINGS SIDE BY SIDE on one ground line: the press on the left, and on the "
 "right A SCHOLAR'S WORKING DESK. "
 "Remove the three flying pages and their speed lines. Draw the desk as standing equipment with NO person at it: "
 "a heavy wooden table bearing a tall CARD-INDEX CABINET of many small drawers with one drawer pulled open and "
 "upright filing cards in it, a sloped reading stand holding one large open volume whose pages are ruled into "
 "dense blank columns, a spike with a sheaf of small slips impaled on it, and a wide ruled LEDGER lying open and "
 "flat, gridded into empty columns and rows. "
 "ONE single sheet of paper travels from the press across the gap to the desk, linking the two, so the eye reads "
 "left to right from press to desk. Press and desk occupy roughly equal space, balanced as equals. " + NOTEXT + LANDSCAPE)

V = {'cA': A, 'cB': B, 'cC': C}
log = []
for name in (sys.argv[1:] or list(V)):
    r = client.models.generate_content(
        model='gemini-2.5-flash-image',
        contents=[types.Part.from_bytes(data=src, mime_type='image/png'), V[name]])
    u = r.usage_metadata; ok = False
    for p in r.candidates[0].content.parts:
        if getattr(p, 'inline_data', None) and p.inline_data.data:
            open(os.path.join(HERE, f'{name}.png'), 'wb').write(p.inline_data.data); ok = True
    rec = dict(name=name, saved=ok, prompt_tokens=u.prompt_token_count,
               output_tokens=u.candidates_token_count, total=u.total_token_count)
    print(json.dumps(rec)); log.append(rec)
json.dump(log, open(os.path.join(HERE, 'usage_consume.json'), 'w'), indent=1)

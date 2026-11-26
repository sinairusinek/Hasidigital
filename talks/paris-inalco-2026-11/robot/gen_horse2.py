"""Round 2 of the four wordless panels for Shivhei ha-Besht no. 11 (the stolen horse).

Changes from gen_horse.py, per Sinai:
  - less photographic realism, more of a comic / broadside woodcut; all four panels
    must look like ONE hand on ONE day (shared line weight, same figure scale).
  - no numerals, no captions anywhere -- they are laid out as a 2x2 grid instead.
  - panel 1: hurried stealth.
  - panel 2: the emblem is a CRYPTIC WORD-SHAPE (not a legible horse), and BOTH men
    are surprised.
  - panel 3: no thought bubble at all, just plainer ridicule.
  - panel 4: horse and Besht smiling at each other, the gentile surprised.

Output h*_b.png so round 1 (h*.png) is kept for comparison.
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

# One style block, repeated verbatim in all four, so the set coheres.
STYLE = (
    "Style: a woodcut comic panel from an old printed chapbook, black ink on warm cream paper, "
    "slight sepia tone. SIMPLIFIED AND STYLISED, NOT REALISTIC: bold confident outlines of even weight, "
    "flat areas of plain cream and plain black, simple blocky cross-hatching used sparingly for shadow only. "
    "Faces are simplified and expressive, almost cartoon-like, with clear readable emotion -- big plain eyes, "
    "strong eyebrows, simple mouths -- but drawn with dignity, never grotesque or caricatured, and never "
    "mocking any religion or people. No fine engraving detail, no photographic texture, no realistic "
    "modelling of cloth or skin, no gradients, no colour wash. "
    "All figures are drawn at the same size and in the same simple style in every panel, as if by one "
    "artist for one book. Medium shot: the figures fill the panel from roughly the knees up. "
    "ABSOLUTELY NO LETTERS, WORDS, NUMBERS, TITLES, LABELS, CAPTIONS OR SIGNATURES ANYWHERE IN THE IMAGE. "
    "A single square panel, one scene, filling the whole image edge to edge, with NO frame, NO ruled border "
    "and NO paper margin around it."
)

CAST = (
    "Recurring cast, drawn identically in every panel: THE BESHT is a stocky bearded Jewish man of middle "
    "age in a long dark coat and a round fur-trimmed hat, warm and open-faced. THE BROTHER-IN-LAW is "
    "taller and leaner, a Jewish scholar with a short dark beard, a long dark coat and a flat broad-brimmed "
    "hat. THE HORSE is one plain pale working horse with a dark mane. Setting: an eighteenth-century "
    "Eastern European small town of simple wooden houses. "
)

PANELS = {
 'h1_b': CAST + "PANEL ONE -- HURRIED STEALTH AT NIGHT. A thief in a hooded cloak, face hidden in shadow, "
   "is stealing the horse from the stable and is in a great hurry: he is caught mid-stride, leaning far "
   "forward, almost running, hauling the horse by the halter with both hands and throwing a sharp glance "
   "back over his shoulder to see if anyone is watching. The horse is pulled along off-balance with its "
   "head stretched out. Convey haste and furtiveness: a tilted leaning composition, the stable door left "
   "banging open behind him, scattered straw, a few speed lines and dust puffs at his heels in the simple "
   "woodcut manner. Night: a dark sky with a thin crescent moon, the houses in flat black silhouette. "
   "No other people. ",

 'h2_b': CAST + "PANEL TWO -- THE WORD ESCAPES. Indoors, a bare wooden room, the two men facing each other. "
   "Out of the Besht's open mouth flies a small round emblem, like a sealed medallion, trailed by three "
   "little circles as an utterance is drawn in old prints. Inside that medallion there is NO picture of "
   "anything recognisable: it holds a single CRYPTIC MARK, an invented occult sigil of a few strokes, a "
   "curl and a dot -- deliberately unreadable, resembling no real alphabet and no real letter, like a "
   "secret seal. BOTH MEN ARE ASTONISHED and both stare at the flying emblem, not at each other: the Besht "
   "has flung one hand to his own mouth, his eyes wide, startled that the word left him at all; the "
   "brother-in-law has recoiled a step with his eyebrows high, his arms starting to unfold, his mouth "
   "open. Strong simple expressions of shock on both faces. ",

 'h3_b': CAST + "PANEL THREE -- OPEN RIDICULE IN THE STREET. Broad daylight in the town lane. "
   "NO thought bubble and no emblem of any kind anywhere in this panel -- the air above them is empty sky. "
   "The brother-in-law is plainly jeering at the Besht: head thrown back, mouth wide in a big laugh, one "
   "hand slapping his own thigh and the other arm flung out to point mockingly at the bare empty ground "
   "beside the Besht where a horse obviously is not. He leans in toward the Besht as he laughs. "
   "Two or three townsfolk stand behind them, grinning and nudging each other, joining in the laughter. "
   "The Besht stands square and quiet in the middle of it, hands at his sides, patient and unbothered. "
   "The ridicule must read instantly from the postures alone. ",

 'h4_b': CAST + "PANEL FOUR -- THE RETURN, the happiest panel. We are INSIDE the Besht's house, looking "
   "at the back wall of the room. That wall has one big open window. THE HORSE IS OUTSIDE IN THE STREET, "
   "NOT in the room: only its HEAD AND NECK come in through the window opening. The horse's body, legs "
   "and hooves are NOT visible inside the room -- the window sill cuts across its neck. Never draw a whole "
   "horse standing on the floorboards indoors. "
   "Sitting on the horse's back outside, visible through the window above and behind the horse's head, is "
   "a peasant gentile in a sheepskin coat and cap holding out a long clay pipe he came to have lit. "
   "HE IS THE SURPRISED ONE: eyes wide, eyebrows up, jaw dropped, the pipe frozen halfway from his mouth "
   "as he stares down at the man and the horse greeting each other like old friends. "
   "The Besht stands inside at the window, face to face and nose to nose with the horse's head: THE BESHT "
   "AND THE HORSE ARE BOTH SMILING BROADLY AT EACH OTHER WITH OPEN DELIGHT -- the man beaming, both hands "
   "cupped on the horse's muzzle; the horse's ears pricked forward, its eye bright and its mouth curved up "
   "in a happy horse-smile, stretching eagerly in toward him. "
   "To the other side, inside the room, the brother-in-law stands thunderstruck: eyes wide, mouth open, "
   "one hand half-raised. A lit candle stands on a small table indoors. "
   "KEEP THIS PANEL BRIGHT AND OPEN, mostly plain cream paper with black outlines and only small areas of "
   "solid black, matching the lightness of the other panels. ",
}

which = sys.argv[1:] or list(PANELS)
log = []
for name in which:
    r = client.models.generate_content(model=MODEL, contents=PANELS[name] + STYLE)
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
json.dump(log, open(os.path.join(HERE, 'usage_horse2.json'), 'w'), indent=1)

"""Four wordless comic panels for Shivhei ha-Besht no. 11 (the stolen horse).

Same house style as m1_press_engraving.png and f2.png (the five-scholars table plate):
19th-century wood engraving, black ink cross-hatching on warm cream paper.
NO text is asked of the model -- it renders letters badly. Any caption lives in the
HTML slide (horse_slide.html) as vector type, exactly as table_slide.html does.

Story (Shivhei-Habesht_0011): the Besht had a horse and it was stolen. R' Gershon
(his brother-in-law) was rebuking him, and a word was suddenly flung from his mouth:
the horse will be returned to him. R' Gershon laughed at him and every time he came
to town he taunted him -- "Israel, have they returned your horse?" For about a year
there was no horse. In the end a gentile came riding on that same horse and knocked
at the window to be given a light for his pipe, and he recognised his horse and said,
is this not my horse -- and at once he got down from the horse and returned it to him.
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
    "on plain warm cream paper, slight sepia tone, like an illustration in an old book of tales. "
    "No colour wash, no modern shading, no photographic realism. Respectful and witty, gently humorous, "
    "never caricature or mockery of any religion or people; the Jewish figures are dignified. "
    "ABSOLUTELY NO LETTERS, WORDS, NUMBERS, TITLES, LABELS, SPEECH BALLOONS WITH WRITING, CAPTIONS OR "
    "SIGNATURES ANYWHERE IN THE IMAGE. Book pages and signs must be blank or show only abstract squiggles. "
    "A single square panel, one scene only, generous cream margins, a thin plain ruled border around the scene."
)

CAST = (
    "Recurring cast, drawn identically in every panel so they are recognisable: "
    "THE BESHT is a sturdy bearded Jewish man of middle age in a long dark coat and a fur-trimmed hat, "
    "calm and warm-faced. THE BROTHER-IN-LAW is a leaner, taller, clean-featured Jewish scholar with a "
    "short beard, a dark coat and a broad-brimmed hat, sharp and sceptical. THE HORSE is a single plain "
    "working horse, light-coated with a dark mane, no markings. Eighteenth-century Eastern European "
    "small-town setting: wooden houses, shingled roofs, an unpaved lane. "
)

PANELS = {
 'h1': CAST + "PANEL ONE: night in the lane behind a wooden house. A thief in a hooded cloak, seen from "
   "behind and in shadow so his face is hidden, is leading the horse away out of an open stable door. "
   "The stable is left empty and dark, the door swinging. Nobody else is present; the house windows are "
   "shuttered. The mood is quiet theft, moonlight and long cross-hatched shadows. ",

 'h2': CAST + "PANEL TWO: indoors by day. The Besht stands in mid-speech, and he himself looks startled "
   "by what he has just said -- his eyebrows raised, one hand half-lifted and open as if the words escaped "
   "him rather than were chosen. From his open mouth a small wordless emblem flies outward and upward "
   "through the air like a thing thrown: a tiny engraved picture of the horse, inside a small round "
   "medallion trailed by a few little circles, as a thought or utterance is drawn in old prints. "
   "The brother-in-law stands opposite with his arms folded, in the middle of rebuking him. "
   "Emphasise the Besht's surprise at his own mouth. ",

 'h3': CAST + "PANEL THREE: the lane in the small town, broad daylight, a few townsfolk passing. "
   "The brother-in-law has stopped the Besht in the street and is mocking him: he is laughing openly, "
   "head tipped back, one hand on his hip and the other making a wide sweeping gesture at the empty road "
   "beside the Besht where a horse plainly is not. Behind him, over his shoulder, floats a small thought "
   "bubble in the same engraved line style containing nothing but an empty halter and a bare patch of "
   "ground -- the absent horse. The Besht stands quietly, unruffled, taking it. ",

 'h4': CAST + "PANEL FOUR, the punchline, the richest panel: the interior of the Besht's house seen from "
   "inside, with a large open window in the back wall. Framed in that window, outside, a peasant gentile "
   "in a sheepskin coat and a cap sits mounted on the horse, leaning in and holding out a long clay pipe, "
   "asking for a light; he looks ordinary and friendly, not villainous. The horse's head and neck come "
   "right in through the window opening into the room. The Besht, inside, has risen and is face to face "
   "with the horse, the two of them looking straight at each other with unmistakable mutual delight -- "
   "the man smiling broadly with both hands coming up to the horse's muzzle, the horse's ears pricked "
   "forward, its head stretched eagerly toward him, an almost smiling horse. Beside them the "
   "brother-in-law stands frozen in astonishment: eyes wide, mouth open, one hand half-raised, his "
   "sceptical posture collapsed into bewilderment and dawning respect. He looks at the Besht, not at "
   "the window. A candle or hearth gives the light that was asked for. ",
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
json.dump(log, open(os.path.join(HERE, 'usage_horse.json'), 'w'), indent=1)

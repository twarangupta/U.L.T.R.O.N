# Training the "Hey Ultron" wake word

openWakeWord only ships a "hey_jarvis" model, so ULTRON needs a custom model for "Hey Ultron". You train it once, for free, in Google Colab. You do not record your own voice: the notebook makes thousands of synthetic voice clips of the phrase with a text-to-speech engine and trains on those.

Until you finish, ULTRON keeps working with "Hey Jarvis". It switches to "Hey Ultron" automatically as soon as the model file is in place.

Checked against openWakeWord 0.6.0 and its README on 2026-11-15. Colab layouts change; if a step looks different, follow the notebook's own text.

---

## What you need

- A Google account (for Colab).
- About 1 hour, most of it waiting. The notebook says clip generation alone takes about 10 minutes on a free T4 GPU; training adds more.
- Nothing installed on your laptop. Training only runs on Linux, which is why we use Colab instead of Windows.

---

## Step by step

### 1. Open the notebook

Open the "simple" training notebook linked from the openWakeWord README (section "Training New Models"):

https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing

Sign in with your Google account. Click "Copy to Drive" if Colab offers it, so your settings are saved.

### 2. Switch on the GPU

Menu: Runtime > Change runtime type > Hardware accelerator: T4 GPU > Save.

Without a GPU it still works but takes much longer.

### 3. Set the target phrase

Find the cell or form field for the wake phrase (in the detailed notebook it is `target_phrase`, and the model name is built from it). Set:

- target phrase: `hey ultron`
- model name (if asked separately): `hey_ultron`

Keep the other settings at their defaults for the first try. Higher sample and step counts (`n_samples`, `steps`) give a better model but take longer.

### 4. Run everything

Menu: Runtime > Run all. Accept the warning that the notebook is not authored by Google.

Leave the tab open. If Colab asks "Are you still there?", click it, or the session stops.

### 5. Download the model

When it finishes, the notebook saves the model in its output folder (named after the model, for example `my_custom_model/hey_ultron.onnx`, plus a `.tflite` version).

Download the `.onnx` file: use the notebook's download step if it has one, or open the Files panel on the left (folder icon), find the file, right-click > Download.

### 6. Put it where ULTRON looks

Save the file as:

```
C:\Twaran files\Misc\J.A.R.V.I.S-main\models\hey_ultron.onnx
```

The name must be exactly `hey_ultron.onnx`. The `models` folder is ignored by git, so the file will not be committed.

Note: the downloaded file may be named after the phrase you typed, for example `hey_ultron.onnx` already. If it is named something else, rename it.

### 7. Test it

```
python ultron.py
```

The log should say `Wake phrase: "Hey Ultron"` and the sleeping line should say `Say "Hey Ultron" to wake me`. If it still says Hey Jarvis, the file is not in the right place or has the wrong name.

Then:

1. Say "Hey Ultron" 10 times at normal volume from your usual seat. Count how many wake it. Aim for 9 or 10.
2. Talk normally, play a video or music for 15 to 30 minutes. Count false wake-ups. Aim for none, at most one.
3. Try "Hey Ultron" from across the room and with a fan or music on.

Every trigger is logged with a confidence score, for example `Wake Word Triggered. Confidence: 0.83`. Those numbers are what you tune with.

---

## Tuning the threshold

The threshold is how sure the model must be before ULTRON wakes. Higher means fewer false wake-ups but more missed "Hey Ultron"s. openWakeWord's default is 0.5 and its README recommends finding the best value by testing in your own room.

Set it in a `.env` file in the project folder (or as an environment variable):

```
WAKE_WORD_THRESHOLD=0.5
```

- Misses your real "Hey Ultron" too often: lower it in steps of 0.1 (0.4, 0.3).
- Wakes up by itself: raise it in steps of 0.1 (0.6, 0.7).

Note: today's default is still 0.2, which was set for the Jarvis model. The tune/wake-threshold branch moves it to 0.5. With your own model, start at 0.5.

---

## If accuracy is poor

Try these in order. Each one means training again (step 3 onward).

1. More training. Raise `n_samples` and `steps` (for example double them). Slower, usually better.
2. Spell the phrase the way it sounds. The text-to-speech voices may say "ultron" oddly (for example "ul-TRON" with the wrong stress, or "ultra-on"). Listen to a few generated clips if the notebook plays any, then try spellings such as:
   - `hey ul tron`
   - `hey ultrawn`
   - `hey ull tron`
   Keep the model name `hey_ultron` whichever spelling you use. These spellings are our suggestion, not something the notebook documents; compare results with the test in step 7.
3. Fewer false wake-ups. In the detailed notebook, the setting that punishes false activations is `max_negative_weight` (default 1500). Raising it reduces false wake-ups at some cost to hit rate. You can also list phrases that sound close and should NOT wake it (`custom_negative_phrases`), for example "hey ultra", "hey alton", "hey hilton".
4. A custom verifier. openWakeWord can add a small second-stage model trained on a few clips of your own voice, which cuts false wake-ups a lot. We can add this as a later ULTRON branch if needed.

---

## Using a different file or going back to Jarvis

- Another model file: set `WAKE_WORD_MODEL=C:\path\to\model.onnx` in `.env`.
- Force the old phrase: set `WAKE_WORD_MODEL=hey_jarvis`.
- Remove the override and ULTRON goes back to using `models\hey_ultron.onnx` if it exists, else Hey Jarvis.

---

## Licence note

openWakeWord's own pre-trained models are licensed CC BY-NC-SA 4.0 (non-commercial) because of their training data. The README does not state a licence for models you train yourself, and training uses third-party datasets with their own terms. Fine for personal use; check the dataset licences before shipping the model inside a public installer.

# Market Gaps and User Personas

## Market Gaps

Voice products are no longer just basic dictation, but the market is still split between **voice-to-text, AI conversation and computer control**. The bigger gap is what happens between speaking and actually working with what is already on the screen.

| Product | What it does well | Gap / opportunity for Kivi |
|---|---|---|
| **Wispr Flow** | Fast system-wide voice typing, natural speech, formatting and context across apps. | Still primarily optimises the path from speech to written output. Kivi can make the **screen itself the context**: select something, speak about it, preview the change and apply it. |
| **Superwhisper** | Strong transcription, custom modes, many languages and local/offline options. | Powerful but increasingly feels like a configurable dictation system. Kivi can hide model/mode complexity and focus on **voice + screen + intent**. |
| **TalkTastic** | Voice input and AI-assisted writing inside the typing workflow. | The interaction still starts with a text field. Kivi can start from **anything on the screen**, not only where the cursor is. |
| **Microsoft Copilot** | Voice conversation, work/web grounding and deep Microsoft ecosystem integration. | More **assistant-first** than interaction-layer-first. Kivi can begin with the exact sentence, code, email or content the user is looking at. |
| **Gemini Live** | Natural spoken conversation and back-and-forth interaction with AI. | Strong as an AI conversation, but not designed primarily as a **system-wide layer for transforming the user's current screen context**. |
| **ChatGPT Voice** | Very natural voice conversation, explanations and brainstorming. | The user generally enters an AI conversation. Kivi's opportunity is to make voice work **inside the user's existing workflow**, without turning every interaction into a chat. |
| **Windows Voice Typing / Voice Access** | Native dictation plus voice control, navigation and text editing across Windows. | Excellent computer control, but commands are still largely explicit. Kivi can interpret **natural intent** around the selected content instead of making users learn command syntax. |
| **Gboard** | Fast voice typing, multilingual input and voice-based rewriting/proofreading features. | Strong keyboard-level input, but still centred on composing text. Kivi can extend the same idea into **understanding, transforming and communicating**, not just typing. |

### The bigger gap

**1. Voice tells the computer what you said. The screen tells it where. The missing layer is what you mean.**

Most products optimise one of these relationships:

- **Dictation:** voice → text
- **AI assistants:** voice → conversation
- **Computer control:** voice → command
- **AI voice typing:** voice → cleaner text

Kivi can connect them differently:

**WHERE → the screen / selection**  
**WHAT → the user's voice**  
**MEANING → Kivi**  
**RESULT → the app the user is already using**

That creates interactions such as:

- Select a paragraph → *"Explain this like I'm a first-year student."*
- Select code → *"Add a check here so this doesn't crash on empty input."*
- Select a message → *"Make this more respectful, but keep my meaning."*
- Select an email → *"Turn this into a three-line Slack update."*
- Speak in Tanglish → get a clean English note without manually switching languages.
- Speak once → create different versions for Slack, email and WhatsApp.

### 2. Multilingual speech is still treated too much like a setting

Most voice products treat language as something the user selects. But real Indian speech is often mixed: **Tamil + English, Hindi + English, Kannada + English, Tanglish**, and more. The larger product opportunity is to make multilingual understanding part of the interaction itself rather than a separate input mode.

Kivi can make language a layer across every action: **Think, Write, Understand, Communicate and Remember**. The user should be able to speak naturally and let Kivi decide how the output needs to be expressed.

### 3. Voice is still mostly an input method

The market is getting better at **voice → text** and **voice → AI response**, but there is more room for **voice → useful output**. Kivi can return a structured note, edited text, translated message, spoken explanation, code change or reminder depending on the intent. This makes voice a general interface rather than another keyboard.

### 4. Personalisation is mostly about output, not behaviour

Dictionaries, custom vocabulary, styles and correction learning already make voice products better at recognising a user. The deeper opportunity is for Kivi to learn **how that person works**: their terminology, preferred tone, recurring shortcuts, languages, formatting preferences and common workflows. Memory should make future interactions feel more natural without silently changing the user's intent.

### Where Kivi can own the whitespace

**Kivi is not trying to beat every competitor at transcription, conversation or computer control.** Its wedge is the combination:

**Voice + Screen Context + Intent + Multilingual Understanding + Personalisation**

The simple product promise becomes:

> **Don't explain the interface. Tell Kivi what you mean.**

### Market snapshot

| Category | Typical interaction | Kivi's difference |
|---|---|---|
| Traditional dictation | "Type what I say" | "Understand what I mean" |
| AI voice typing | "Clean up what I said" | "Change what I selected in the way I asked" |
| AI voice assistant | "Talk to the AI" | "Work with what is already in front of me" |
| Computer voice control | "Press / open / click X" | "Express the intent naturally" |
| **Kivi** | **Screen + voice + intent** | **The voice layer for computing** |

## User Personas - Mapped to Kivi's Proposed features

### 1. Ananya, 21 - Student

Ananya is usually reading a paper while replying to messages and working on an assignment. She often speaks in a mix of Tamil and English, but her college work usually needs to be in English. When she doesn't understand a paper, she copies parts of it into an AI tool. She also spends a lot of time rewriting messages to professors because she knows what she wants to say but isn't sure how formal it should sound.

**How Kivi fits:** She can select a difficult part of a paper and ask Kivi to explain it. She can speak her thoughts in Tanglish and turn them into notes, or ask Kivi to make a message suitable for a professor. She can also listen to explanations instead of stopping to read everything. Over time, Kivi can learn the names and terms she uses often.

**Main Kivi use cases:** Understand, Think, Communicate, multilingual speech, TTS, Green Selection, Styles and Memory.

### 2. Arjun, 26 - Software Developer

Arjun spends most of his day in Cursor, GitHub, Slack and documentation. He is fine with writing code, but doesn't want to type a long prompt every time he needs a small change. He also doesn't like having to leave his editor just to understand a piece of code or check some documentation.

**How Kivi fits:** He can select a few lines of code and say what he wants changed. Kivi can show the proposed change and let him apply it. If he finds a function he doesn't understand, he can ask for an explanation without leaving the editor. He can also set up shortcuts for things he does often and create a mode for the way he likes to work.

**Main Kivi use cases:** Write, Understand, Kivi Anywhere, Green Selection, coding, Shortcuts, Modes and learning from corrections.

### 3. Rohan, 29 - Communication-heavy Professional

Rohan usually knows what he wants to say. The annoying part is saying the same thing differently to different people. A project delay might become a short Slack message, a proper email to a client and a casual WhatsApp message. He also works with people who are more comfortable speaking different Indian languages.

**How Kivi fits:** Rohan can say the thought once and ask Kivi to adapt it for different people and apps. He could speak a voice message in Tamil and have it come out in Hindi, or use speech-to-speech translation during a conversation. He can also make shortcuts for things he does regularly, such as preparing something in his usual client tone.

**Main Kivi use cases:** Communicate, Kivi Mic, multilingual STS, voice messages, Styles, Shortcuts and personalization.

## What These Personas Show

The three personas use Kivi differently. Ananya needs help understanding and writing. Arjun wants to make changes without breaking his coding flow. Rohan wants to communicate the same idea in different ways. What connects them is that they already know what they want to do. They just don't want typing and app interfaces to get in the way.

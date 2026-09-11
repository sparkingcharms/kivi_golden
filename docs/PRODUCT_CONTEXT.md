# Kivi Product Context

This repository is the **Golden Goose implementation of one part of the same Kivi product described in the Product UI/UX work**. The implementation focus here is semantic memory and the Remember intention. It should not be read as a separate product direction.

## Product position

Kivi is a personal multilingual voice layer for people who think, create and communicate more freely than they type. It connects your voice with the context of your computer. The screen tells Kivi where to look, your speech tells it what you want, and Kivi understands the intent. Kivi Anywhere brings this layer across the apps people already use, while Kivi Mic brings Kivi into microphone experiences already inside apps. Across apps, Kivi helps people **Think, Write, Understand, Communicate and Remember**, while keeping them in control.

## Product vision

Kivi's long-term vision is a universal voice layer between people and their computers. People should be able to speak naturally, point at what matters, and let Kivi understand the intent without having to translate their thoughts into the language of software.

The five intentions are:

- **Think** — organise what I am thinking.
- **Write** — create or change what I want to say.
- **Understand** — make sense of what I am receiving.
- **Communicate** — express what I mean appropriately to someone else.
- **Remember** — learn how I work.

The interaction underneath them stays simple:

**Speak → Kivi understands → Kivi helps.**

## UI/UX interaction model

The Kivi wireframes establish the core interaction:

**Point → Speak → Understand → Preview → Apply**

Kivi is a layer over the existing app. The app underneath stays where it is. A selection can become the context, the user supplies the instruction through voice, Kivi makes its interpretation visible, and the user remains responsible for applying a proposed change.

The wireframes cover Kivi Anywhere, Green Selection, Understand, Write, Think, Communicate, code, Remember and the Teaching Kivi window. The Teaching screen brings Styles, Dictionary and Memory together in one place.

**Source wireframes:** [Kivi wireframes.pdf](https://github.com/sparkingcharms/kivi/blob/main/Kivi%20wireframes.pdf)

## Research behind the direction

### User interviews

The interviews surfaced six important themes that led into this product direction:

- understanding context matters more than transcription alone;
- voice is more useful when it knows what is on screen;
- people want AI to learn how they work;
- people expect more than question answering;
- people want an AI companion that is available on the laptop;
- multilingual interaction and communication are real needs.

The full interview questions and insights are in [`research/User Interviews.md`](research/User%20Interviews.md).

### Market gaps and personas

The market research identified a gap between dictation, AI conversation and explicit computer control. Kivi's opportunity is the combination of **voice + screen context + intent + multilingual understanding + personalisation** rather than trying to win every category independently.

The three working personas are Ananya (student), Arjun (software developer) and Rohan (communication-heavy professional). They have different use cases but share the same underlying need: they know what they want to do and do not want typing and app interfaces to get in the way.

See [`research/Market Gaps and User Personas.md`](research/Market%20Gaps%20and%20User%20Personas.md).

### Product video

The product video transcript reinforces the same model across writing, coding, understanding, communication, reminders, dictionary, styles, shortcuts, multilingual interaction, Kivi Anywhere and Kivi Mic. See [`research/Product Video Transcript.md`](research/Product%20Video%20Transcript.md).

## Why Golden Goose focuses on Remember

Memory is the layer that makes Kivi personal over time. This repository therefore goes deep on **Remember** rather than trying to implement every Kivi capability superficially.

The semantic-memory implementation should strengthen the broader Kivi product without changing its identity:

- ordinary dictation remains ordinary dictation;
- learned words can fix Kivi's own transcription errors;
- Hey Kivi can use broader memory when the user asks for help;
- important interpretations are visible;
- uncertain inferences are not silently applied;
- proposed changes remain previews until the user applies them;
- Kivi never sends or posts on the user's behalf;
- sensitive information is not stored;
- memory can be traced back to where it came from and removed.

## Consistency rule for future work

When adding functionality to this repository, ask:

1. Does it fit **Kivi as a layer**, rather than turning Kivi into a destination?
2. Does it preserve **voice + screen context + intent**?
3. Does it fit one or more of **Think, Write, Understand, Communicate, Remember**?
4. Does the user remain in control?
5. Does the interaction feel like the existing Kivi pattern rather than a separate AI product?

If the answer is no, the feature should not be added merely because it is technically possible.

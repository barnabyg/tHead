# Evaluation audio provenance

`reference-1089-10s.wav`: Peter Bobbe, LibriVox reader 1089, LibriSpeech test-clean
utterance `1089-134691-0009`, first 160,000 decoded mono samples at 16,000 Hz.
Converted from FLAC to PCM16 WAV, no other processing. Original duration 20.055 s.

Source: [LibriSpeech / OpenSLR 12](https://www.openslr.org/12), prepared by
Vassil Panayotov, Daniel Povey, Guoguo Chen and Sanjeev Khudanpur from LibriVox
read audiobooks. Corpus licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Downloaded 8 November 2026 from `https://www.openslr.org/resources/12/test-clean.tar.gz`.

Archive SHA-256:
`39fde525e59672dc6d1551919b1478f724438a95aa55f874b576be21967e6c23`.
Original `LibriSpeech/test-clean/1089/134691/1089-134691-0009.flac` SHA-256:
`11b43ade12501f613e4d81b5f4ab18f0f751d8ce8fd60130cd66f0cb8fdbedc0`.

The original transcript begins with the reader describing someone looking into
water under a bridge. It does not contain the new local text-to-speech baseline
passage. Full transcript is obtainable in the same archive's chapter transcript.

`setup-speech.wav` is **synthetic speech**, produced locally from this excerpt
and the text/settings in `setup-result.json`. It is not an original recording
of Peter Bobbe saying that passage and does not imply endorsement. Upstream
Perth watermarking was retained. Code/model pins and limitations are in the
[evaluation report](../chatterbox-evaluation.md).

## Quality reference excerpts (#53)

`reference-1089-20s.wav`: first 320,000 decoded samples (20 seconds) of the same
Peter Bobbe utterance, from James Joyce's *Portrait of the Artist as a Young Man*,
chapter 4 part 2. Original duration 20.055 seconds; hash above.

`reference-121-20s.wav`: Nikolle Doolin, reader 121, LibriSpeech test-clean
`121-123852-0003.flac`, first 320,000 decoded samples (20 seconds) of a 23.505-second
recording of Shakespeare's *Sonnets*, section Sonnets 41–50. Original FLAC SHA-256:
`5a10c9d928483a6850edfdac439751bae191b7af126165627d330bc83bc6083e`.
Same corpus, source archive, authors and CC BY 4.0 attribution as above. Neither
excerpt is a private recording. Recording equipment/acoustic conditions are unknown.
The corpus's broad US-accent classification is automated and explicitly unreliable;
neither reader's accent has been independently classified in this evaluation.

The quality-pack command crops these excerpts to 5/10/20 seconds without other
processing for clean conditions. It also adds deterministic nominal 15 dB Gaussian
noise (seed 20261108) to Peter Bobbe's first 10 seconds, and constructs a two-speaker
example from his first 5 seconds followed by Nikolle Doolin's first 5 seconds.
These transformations are labelled in the pack. Generated cloning examples are
synthetic research audio and do not imply either reader's endorsement.

// audio-processor.js — AudioWorklet processor for PCM16 capture
class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Int16Array(0);
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input.length > 0) {
      const channelData = input[0]; // Float32Array, mono
      const pcm16 = new Int16Array(channelData.length);
      for (let i = 0; i < channelData.length; i++) {
        const s = Math.max(-1, Math.min(1, channelData[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }

      // Buffer chunks to ~100ms (2400 samples at 24kHz)
      const combined = new Int16Array(this._buffer.length + pcm16.length);
      combined.set(this._buffer, 0);
      combined.set(pcm16, this._buffer.length);
      this._buffer = combined;

      while (this._buffer.length >= 2400) {
        const chunk = this._buffer.slice(0, 2400);
        this._buffer = this._buffer.slice(2400);
        this.port.postMessage(chunk, [chunk.buffer]);
      }
    }
    return true;
  }
}

registerProcessor("audio-capture-processor", AudioCaptureProcessor);

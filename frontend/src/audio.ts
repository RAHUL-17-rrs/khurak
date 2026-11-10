/** Browser audio helpers: record the mic as 16-bit PCM WAV (no ffmpeg needed server-side),
 *  and play a queue of clips one after another. */

export interface Capture { blob: Blob; peak: number; seconds: number; device: string }

export class WavRecorder {
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private node: ScriptProcessorNode | null = null
  private sink: GainNode | null = null
  private chunks: Float32Array[] = []
  private rate = 16000
  private peak = 0
  level = 0

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: true },
    })
    this.ctx = new AudioContext()
    // Chrome may hand back a suspended context; without this the processor never fires.
    if (this.ctx.state === 'suspended') await this.ctx.resume()
    this.rate = this.ctx.sampleRate
    const src = this.ctx.createMediaStreamSource(this.stream)
    this.node = this.ctx.createScriptProcessor(4096, 1, 1)
    this.chunks = []
    this.peak = 0
    this.node.onaudioprocess = (e) => {
      const d = e.inputBuffer.getChannelData(0)
      this.chunks.push(new Float32Array(d))
      let s = 0
      for (let i = 0; i < d.length; i += 16) {
        s += d[i] * d[i]
        const a = Math.abs(d[i])
        if (a > this.peak) this.peak = a
      }
      this.level = Math.min(1, Math.sqrt(s / (d.length / 16)) * 4)
    }
    src.connect(this.node)
    // A silent sink keeps the processor pulling. Connecting straight to destination would send the
    // microphone back out of the speakers, and the echo canceller then treats the speaker's voice as
    // echo of the mic and mutes it, so the whole answer arrives as silence.
    this.sink = this.ctx.createGain()
    this.sink.gain.value = 0
    this.node.connect(this.sink)
    this.sink.connect(this.ctx.destination)
  }

  async stop(): Promise<Capture> {
    const device = this.stream?.getAudioTracks()[0]?.label || 'unknown microphone'
    this.node?.disconnect()
    this.sink?.disconnect()
    this.stream?.getTracks().forEach((t) => t.stop())
    await this.ctx?.close()
    const len = this.chunks.reduce((a, c) => a + c.length, 0)
    const pcm = new Float32Array(len)
    let o = 0
    for (const c of this.chunks) { pcm.set(c, o); o += c.length }
    return { blob: encodeWav(pcm, this.rate), peak: this.peak, seconds: len / this.rate, device }
  }
}

export function encodeWav(samples: Float32Array, rate: number): Blob {
  const buf = new ArrayBuffer(44 + samples.length * 2)
  const v = new DataView(buf)
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)) }
  w(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); w(8, 'WAVE'); w(12, 'fmt ')
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true)
  v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data')
  v.setUint32(40, samples.length * 2, true)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Blob([buf], { type: 'audio/wav' })
}

let current: HTMLAudioElement | null = null

/** Play one clip; resolves when it ends (or fails). Stops whatever was playing. */
export function play(url: string | null | undefined): Promise<void> {
  return new Promise((resolve) => {
    if (!url) return resolve()
    current?.pause()
    const a = new Audio(url)
    current = a
    a.onended = () => resolve()
    a.onerror = () => resolve()
    a.play().catch(() => resolve())
  })
}

export async function playAll(urls: (string | null | undefined)[], gapMs = 250) {
  for (const u of urls) {
    if (!u) continue
    await play(u)
    await new Promise((r) => setTimeout(r, gapMs))
  }
}

export function stopAudio() { current?.pause() }

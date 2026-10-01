import { useCallback, useEffect, useRef, useState } from 'react'

function downsampleToPcm16(input: Float32Array, inputRate: number, outputRate = 16000) {
  const ratio = inputRate / outputRate
  const outputLength = Math.max(1, Math.round(input.length / ratio))
  const output = new Int16Array(outputLength)
  let writeIndex = 0
  let readOffset = 0

  while (readOffset < input.length) {
    const nextOffset = Math.min(input.length, Math.round((writeIndex + 1) * ratio))
    let sum = 0
    let count = 0
    for (let index = readOffset; index < nextOffset; index += 1) {
      sum += input[index]
      count += 1
    }
    const sample = Math.max(-1, Math.min(1, count ? sum / count : 0))
    output[writeIndex] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
    writeIndex += 1
    readOffset = nextOffset
  }

  return output.buffer
}

export function usePcmRecorder(onChunk: (chunk: ArrayBuffer) => void) {
  const [isRecording, setIsRecording] = useState(false)
  const callbackRef = useRef(onChunk)
  const streamRef = useRef<MediaStream | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)

  useEffect(() => {
    callbackRef.current = onChunk
  }, [onChunk])

  const stop = useCallback(() => {
    processorRef.current?.disconnect()
    sourceRef.current?.disconnect()
    streamRef.current?.getTracks().forEach((track) => track.stop())
    void contextRef.current?.close()
    processorRef.current = null
    sourceRef.current = null
    streamRef.current = null
    contextRef.current = null
    setIsRecording(false)
  }, [])

  const start = useCallback(async () => {
    if (isRecording) return
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
    const context = new AudioContext()
    const source = context.createMediaStreamSource(stream)
    const processor = context.createScriptProcessor(4096, 1, 1)

    processor.onaudioprocess = (event) => {
      const samples = event.inputBuffer.getChannelData(0)
      callbackRef.current(downsampleToPcm16(samples, context.sampleRate))
    }
    source.connect(processor)
    processor.connect(context.destination)

    streamRef.current = stream
    contextRef.current = context
    sourceRef.current = source
    processorRef.current = processor
    setIsRecording(true)
  }, [isRecording])

  useEffect(() => stop, [stop])

  return { start, stop, isRecording }
}

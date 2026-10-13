// AudioWorklet: hands each 128-sample block of the microphone to the page. Plain JS (the worklet scope has no module system or TS).
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0]
    if (channel && channel.length) this.port.postMessage(channel.slice(0))
    return true
  }
}
registerProcessor('voxam-capture', CaptureProcessor)

import { useEffect, useState } from 'react';

type NetworkState = 'online' | 'offline' | 'unknown';
let state: NetworkState = 'unknown';
const listeners = new Set<(value: NetworkState) => void>();

export function setNetworkState(value: NetworkState) {
  if (state === value) return;
  state = value;
  listeners.forEach((listener) => listener(value));
}

export function useNetworkState() {
  const [value, setValue] = useState<NetworkState>(state);
  useEffect(() => {
    listeners.add(setValue);
    return () => { listeners.delete(setValue); };
  }, []);
  return value;
}

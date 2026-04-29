import { useCallback, useEffect, useRef, useState } from "react";
import {
  runIntradayScan,
  type IntradayScanRequest,
  type IntradayScanResult,
} from "../../../lib/api";

export function useScanPolling({
  request,
  autoPoll,
  intervalSeconds,
}: {
  request: IntradayScanRequest;
  autoPoll: boolean;
  intervalSeconds: number;
}) {
  const [scan, setScan] = useState<IntradayScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef(request);
  requestRef.current = request;

  const runScan = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await runIntradayScan(requestRef.current);
      setScan(result);
      return result;
    } catch (err) {
      setError(String(err));
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!autoPoll) return undefined;
    const timer = window.setInterval(() => {
      if (!loading) {
        runScan();
      }
    }, intervalSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [autoPoll, intervalSeconds, loading, runScan]);

  return { scan, loading, error, runScan, setScan };
}

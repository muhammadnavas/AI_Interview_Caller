'use client';

import { useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function Home() {
  const [result, setResult] = useState('');
  const [callLoading, setCallLoading] = useState(false);
  const [callStatus, setCallStatus] = useState<string>('');

  const makeCall = async () => {
    try {
      setCallLoading(true);
      setCallStatus('Initiating call...');

      const response = await fetch(`${API_BASE}/make-actual-call`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      const data = await response.json();

      if (data.status === 'success') {
        setCallStatus(`Call initiated! Call ID: ${data.call_sid}`);
      } else {
        setCallStatus(`Call failed: ${data.message}`);
      }

      setResult(JSON.stringify(data, null, 2));
    } catch (error: any) {
      setCallStatus(`Error: ${error.message}`);
    } finally {
      setCallLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 py-12 px-4">
      <div className="max-w-2xl mx-auto bg-white rounded-lg shadow-lg p-8">
        <h1 className="text-3xl font-bold text-center text-gray-800 mb-8">
          AI Interview Caller
        </h1>

        <div className="mb-6">
          <button
            onClick={makeCall}
            disabled={callLoading}
            className="w-full bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white font-medium py-3 px-6 rounded-lg"
          >
            {callLoading ? 'CALLING...' : 'MAKE CALL'}
          </button>
        </div>

        {callStatus && (
          <div className="mb-4 text-sm text-gray-700 bg-white p-3 rounded border">
            <strong>Status:</strong> {callStatus}
          </div>
        )}

        {result && (
          <pre className="bg-gray-100 p-4 rounded text-sm overflow-x-auto">
            {result}
          </pre>
        )}
      </div>
    </div>
  );
}

export default Home;
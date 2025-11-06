"use client";

import { useEffect, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

export default function Home() {
	const [result, setResult] = useState('');
	const [callLoading, setCallLoading] = useState(false);
	const [callStatus, setCallStatus] = useState('');
	const [systemStatus, setSystemStatus] = useState(null);
	const [conversations, setConversations] = useState([]);
	const [analytics, setAnalytics] = useState(null);
	const [activeTab, setActiveTab] = useState('call');
	const [candidates, setCandidates] = useState([]);
	const [selectedCandidateId, setSelectedCandidateId] = useState('');
	const [candidatesLoading, setCandidatesLoading] = useState(false);

	const fetchSystemStatus = async () => {
		try {
			const response = await fetch(`${API_BASE}/`);
			const data = await response.json();
			setSystemStatus(data);
		} catch (err) {
			console.error('Failed to fetch system status:', err);
		}
	};

	const fetchConversations = async () => {
		try {
			const response = await fetch(`${API_BASE}/conversations`);
			const data = await response.json();
			setConversations(data.conversations || []);
		} catch (err) {
			console.error('Failed to fetch conversations:', err);
		}
	};

	const fetchAnalytics = async () => {
		try {
			const response = await fetch(`${API_BASE}/analytics`);
			const data = await response.json();
			setAnalytics(data);
		} catch (err) {
			console.error('Failed to fetch analytics:', err);
		}
	};

	const fetchCandidates = async () => {
		try {
			setCandidatesLoading(true);
			const response = await fetch(`${API_BASE}/candidates`);
			const data = await response.json();
			if (data.status === 'success') {
				setCandidates(data.candidates || []);
				// Auto-select first candidate if none selected
				if (data.candidates.length > 0 && !selectedCandidateId) {
					setSelectedCandidateId(data.candidates[0].id);
				}
			} else {
				console.error('Failed to fetch candidates:', data.message);
			}
		} catch (err) {
			console.error('Failed to fetch candidates:', err);
		} finally {
			setCandidatesLoading(false);
		}
	};

	useEffect(() => {
		fetchSystemStatus();
		fetchCandidates();
	}, []);

	useEffect(() => {
		if (activeTab === 'conversations') {
			fetchConversations();
			const interval = setInterval(fetchConversations, 5000);
			return () => clearInterval(interval);
		} else if (activeTab === 'analytics') {
			fetchAnalytics();
		}
	}, [activeTab]);

	const makeCall = async () => {
		try {
			setCallLoading(true);
			setCallStatus('Initiating call...');

			// Use selected candidate or fallback to test-call
			const endpoint = selectedCandidateId 
				? `${API_BASE}/call-candidate/${selectedCandidateId}`
				: `${API_BASE}/test-call`;

			const response = await fetch(endpoint, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
			});

			const data = await response.json();
			if (data.status === 'success') {
				setCallStatus(`Call initiated! Call ID: ${data.call_result?.call_sid || 'N/A'}`);
				setTimeout(() => {
					fetchConversations();
					fetchCandidates(); // Refresh candidate status
				}, 2000);
			} else {
				setCallStatus(`Call failed: ${data.message}`);
			}
			setResult(JSON.stringify(data, null, 2));
		} catch (err) {
			const msg = err instanceof Error ? err.message : String(err);
			setCallStatus(`Error: ${msg}`);
		} finally {
			setCallLoading(false);
		}
	};

	const formatTimestamp = (timestamp) => new Date(timestamp).toLocaleString();

	const getStatusBadge = (status) => {
		const colors = {
			active: 'bg-yellow-100 text-yellow-800',
			completed: 'bg-green-100 text-green-800',
			failed: 'bg-red-100 text-red-800',
		};
		return colors[status] || 'bg-gray-100 text-gray-800';
	};

	return (
		<div className="min-h-screen bg-gray-100 py-8 px-4">
			<div className="max-w-6xl mx-auto">
				<div className="bg-white rounded-lg shadow-lg mb-8">
					<div className="border-b border-gray-200">
						<nav className="flex space-x-8 px-8 pt-6">
							{[
								{ key: 'call', label: 'Make Call' },
								{ key: 'conversations', label: 'Conversations' },
								{ key: 'analytics', label: 'Analytics' },
							].map((tab) => (
								<button
									key={tab.key}
									onClick={() => setActiveTab(tab.key)}
									className={`pb-4 px-1 border-b-2 font-medium text-sm ${
										activeTab === tab.key
											? 'border-purple-500 text-purple-600'
											: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
									}`}
								>
									{tab.label}
								</button>
							))}
						</nav>
					</div>

					<div className="p-8">
						{activeTab === 'call' && (
							<div>
								<div className="mb-6">
									<h1 className="text-3xl font-bold text-gray-800 mb-4">AI Interview Caller</h1>
									
									{/* Candidate Selection */}
									<div className="mb-6">
										<div className="flex justify-between items-center mb-4">
											<h3 className="font-semibold text-lg">Select Candidate</h3>
											<button 
												onClick={fetchCandidates}
												disabled={candidatesLoading}
												className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-3 py-1 rounded text-sm"
											>
												{candidatesLoading ? 'Loading...' : 'Refresh'}
											</button>
										</div>
										
										{candidates.length > 0 ? (
											<div className="grid gap-3">
												{candidates.map((candidate) => {
													const canCall = candidate.call_status?.can_call;
													const callReason = candidate.call_status?.reason || '';
													
													return (
														<div 
															key={candidate.id}
															className={`border rounded-lg p-4 cursor-pointer transition-colors ${
																selectedCandidateId === candidate.id 
																	? 'border-purple-500 bg-purple-50' 
																	: canCall 
																		? 'border-gray-200 hover:border-gray-300' 
																		: 'border-red-200 bg-red-50'
															}`}
															onClick={() => canCall && setSelectedCandidateId(candidate.id)}
														>
															<div className="flex justify-between items-start">
																<div className="flex-1">
																	<div className="flex items-center gap-2 mb-2">
																		<input
																			type="radio"
																			name="candidate"
																			value={candidate.id}
																			checked={selectedCandidateId === candidate.id}
																			onChange={() => canCall && setSelectedCandidateId(candidate.id)}
																			disabled={!canCall}
																			className="text-purple-600"
																		/>
																		<h4 className="font-semibold text-lg">{candidate.name}</h4>
																		<span className={`px-2 py-1 rounded-full text-xs font-medium ${
																			canCall ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
																		}`}>
																			{canCall ? 'Available' : 'Unavailable'}
																		</span>
																	</div>
																	<div className="grid grid-cols-2 gap-4 text-sm text-gray-600">
																		<p><strong>Phone:</strong> {candidate.phone}</p>
																		<p><strong>Email:</strong> {candidate.email}</p>
																		<p><strong>Position:</strong> {candidate.position}</p>
																		<p><strong>Company:</strong> {candidate.company}</p>
																	</div>
																	{callReason && (
																		<p className={`text-xs mt-2 ${canCall ? 'text-green-600' : 'text-red-600'}`}>
																			{callReason}
																		</p>
																	)}
																</div>
															</div>
														</div>
													);
												})}
											</div>
										) : (
											<div className="text-center py-8 text-gray-500 border border-gray-200 rounded-lg">
												{candidatesLoading ? 'Loading candidates...' : 'No candidates found. Please add candidates to the database.'}
											</div>
										)}
									</div>
									
									{systemStatus && (
										<div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
											<div className="bg-gray-50 p-4 rounded">
												<h3 className="font-semibold mb-2">Selected Candidate</h3>
												{selectedCandidateId && candidates.length > 0 ? (
													(() => {
														const selected = candidates.find(c => c.id === selectedCandidateId);
														return selected ? (
															<>
																<p><strong>Name:</strong> {selected.name}</p>
																<p><strong>Phone:</strong> {selected.phone}</p>
																<p><strong>Position:</strong> {selected.position}</p>
																<p><strong>Company:</strong> {selected.company}</p>
															</>
														) : <p>No candidate selected</p>;
													})()
												) : (
													<p>No candidate selected</p>
												)}
											</div>
											<div className="bg-gray-50 p-4 rounded">
												<h3 className="font-semibold mb-2">System Status</h3>
												<p>
													<strong>Version:</strong> {systemStatus.version}
												</p>
												<p>
													<strong>Active Calls:</strong> {systemStatus.active_conversations}
												</p>
												<p>
													<strong>Twilio:</strong> {systemStatus.config.twilio_configured ? '✅' : '❌'}
												</p>
												<p>
													<strong>OpenAI:</strong> {systemStatus.config.openai_configured ? '✅' : '❌'}
												</p>
											</div>
										</div>
									)}
								</div>

								<div className="mb-6">
									<button
										onClick={makeCall}
										disabled={callLoading || (!selectedCandidateId && candidates.length > 0)}
										className="w-full bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white font-medium py-3 px-6 rounded-lg"
									>
										{callLoading ? 'CALLING...' : selectedCandidateId ? 
											`CALL ${candidates.find(c => c.id === selectedCandidateId)?.name?.toUpperCase() || 'SELECTED CANDIDATE'}` : 
											'SELECT CANDIDATE TO CALL'
										}
									</button>
									{!selectedCandidateId && candidates.length > 0 && (
										<p className="text-sm text-gray-500 text-center mt-2">
											Please select a candidate from the list above
										</p>
									)}
								</div>

								{callStatus && (
									<div className="mb-4 text-sm text-gray-700 bg-blue-50 p-3 rounded border">
										<strong>Status:</strong> {callStatus}
									</div>
								)}

								{result && (
									<details className="bg-gray-100 p-4 rounded">
										<summary className="cursor-pointer font-medium">Call Response Details</summary>
										<pre className="mt-2 text-sm overflow-x-auto">{result}</pre>
									</details>
								)}
							</div>
						)}

						{activeTab === 'conversations' && (
							<div>
								<div className="flex justify-between items-center mb-6">
									<h2 className="text-2xl font-bold text-gray-800">Conversation History</h2>
									<button onClick={fetchConversations} className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm">
										Refresh
									</button>
								</div>

								{conversations.length === 0 ? (
									<div className="text-center py-8 text-gray-500">No conversations yet. Make a call to get started!</div>
								) : (
									<div className="space-y-4">
										{conversations.map((conversation) => (
											<div key={conversation.call_sid} className="border rounded-lg p-4">
												<div className="flex justify-between items-start mb-3">
													<div>
														<h3 className="font-semibold text-lg">Call {conversation.call_sid.slice(-8)}</h3>
														<p className="text-sm text-gray-600">
															{formatTimestamp(conversation.start_time)}
															{conversation.end_time && ` - ${formatTimestamp(conversation.end_time)}`}
														</p>
													</div>
													<div className="flex items-center space-x-2">
														<span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusBadge(conversation.status)}`}>{conversation.status}</span>
														{conversation.confirmed_slot && <span className="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">{conversation.confirmed_slot}</span>}
													</div>
												</div>

												{conversation.turns.length > 0 && (
													<details className="mt-3">
														<summary className="cursor-pointer text-sm font-medium text-blue-600">View Conversation ({conversation.turns.length} turns)</summary>
														<div className="mt-3 space-y-2 max-h-60 overflow-y-auto">
															{conversation.turns.map((turn, index) => (
																<div key={index} className="text-sm border-l-2 border-gray-200 pl-3">
																	<div className="text-blue-600"><strong>AI:</strong> {turn.ai_response}</div>
																	{turn.candidate_input && (
																		<div className="text-gray-600 mt-1">
																			<strong>Candidate:</strong> {turn.candidate_input}
																			{turn.intent_detected && <span className="ml-2 text-xs bg-gray-100 px-1 rounded">{turn.intent_detected} ({Math.round((turn.confidence_score || 0) * 100)}%)</span>}
																		</div>
																	)}
																</div>
															))}
														</div>
													</details>
												)}
											</div>
										))}
									</div>
								)}
							</div>
						)}

						{activeTab === 'analytics' && (
							<div>
								<h2 className="text-2xl font-bold text-gray-800 mb-6">Analytics Dashboard</h2>
								{analytics ? (
									<div className="space-y-6">
										<div className="grid grid-cols-1 md:grid-cols-4 gap-4">
											<div className="bg-blue-50 p-4 rounded-lg"><h3 className="font-semibold text-blue-800">Total Calls</h3><p className="text-2xl font-bold text-blue-600">{analytics.total_calls}</p></div>
											<div className="bg-green-50 p-4 rounded-lg"><h3 className="font-semibold text-green-800">Success Rate</h3><p className="text-2xl font-bold text-green-600">{analytics.success_rate}%</p></div>
											<div className="bg-yellow-50 p-4 rounded-lg"><h3 className="font-semibold text-yellow-800">Active Calls</h3><p className="text-2xl font-bold text-yellow-600">{analytics.active_calls}</p></div>
											<div className="bg-purple-50 p-4 rounded-lg"><h3 className="font-semibold text-purple-800">Avg Turns</h3><p className="text-2xl font-bold text-purple-600">{analytics.average_turns_per_call}</p></div>
										</div>

										<div className="bg-white border rounded-lg p-6">
											<h3 className="font-semibold text-lg mb-4">Call Outcomes</h3>
											<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
												<div className="text-center"><p className="text-sm text-gray-600">Successful</p><p className="text-xl font-bold text-green-600">{analytics.successful_calls}</p></div>
												<div className="text-center"><p className="text-sm text-gray-600">Failed</p><p className="text-xl font-bold text-red-600">{analytics.failed_calls}</p></div>
												<div className="text-center"><p className="text-sm text-gray-600">Active</p><p className="text-xl font-bold text-yellow-600">{analytics.active_calls}</p></div>
											</div>
										</div>

										{analytics.slot_preferences.length > 0 && (
											<div className="bg-white border rounded-lg p-6">
												<h3 className="font-semibold text-lg mb-4">Preferred Time Slots</h3>
												<div className="space-y-2">
													{analytics.slot_preferences.map((pref, index) => (
														<div key={index} className="flex justify-between items-center"><span>{pref.slot}</span><span className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-sm">{pref.count} bookings</span></div>
													))}
												</div>
											</div>
										)}
									</div>
								) : (
									<div className="text-center py-8 text-gray-500">Loading analytics...</div>
								)}
							</div>
						)}
					</div>
				</div>
			</div>
		</div>
	);
}

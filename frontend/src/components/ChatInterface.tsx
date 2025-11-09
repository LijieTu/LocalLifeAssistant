import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { ChatMessage, ChatRequest } from '../api/client';
import { dataService } from '../services/dataService';
import RecommendationCard from './RecommendationCard';
import { ImageWithFallback } from './ImageWithFallback';
import userAvatarImg from '../assets/images/figma/user-avatar.png';
import agentAvatarImg from '../assets/images/figma/agent-avatar.png';
// import refreshIcon from '../assets/images/figma/refresh-icon.png'; // Hidden for now

interface ChatMessageWithRecommendations {
  role: 'user' | 'assistant';
  content?: string; // Optional to allow undefined for recommendation-only messages
  timestamp?: string;
  recommendations?: any[];
  isRecommendation?: boolean;
  anchorTimestamp?: string | null;
}

interface ChatInterfaceProps {
  onNewMessage: (message: ChatMessage) => void;
  onRecommendations: (recommendations: any[]) => void;
  llmProvider: string;
  conversationHistory: ChatMessage[];
  userId: string;
  onTrialExceeded: () => void;
  conversationId: string | null;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({
  onNewMessage,
  onRecommendations,
  llmProvider,
  conversationHistory,
  userId,
  onTrialExceeded,
  conversationId
}) => {
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [extractionSummary, setExtractionSummary] = useState<string | null>(null);
  const [messagesWithRecommendations, setMessagesWithRecommendations] = useState<ChatMessageWithRecommendations[]>([]);
  const [currentStatus, setCurrentStatus] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const lastAssistantMessageTimestampRef = useRef<string | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
  };

  const scrollToBottomSmooth = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };



  // Scroll to bottom when new content is added (but not for recommendation-only messages)
  useEffect(() => {
    const lastMessage = messagesWithRecommendations[messagesWithRecommendations.length - 1];
    if (lastMessage) {
      // Check if this is a recommendation-only message
      const hasContent = lastMessage.content && lastMessage.content.trim() !== '';
      const isRecommendationOnly = !hasContent && lastMessage.recommendations && lastMessage.recommendations.length > 0;

      // Don't scroll for recommendation-only messages
      if (!isRecommendationOnly) {
        scrollToBottomSmooth();
      }
    }
  }, [messagesWithRecommendations]);

  // Sync with conversation history
  useEffect(() => {
    const syncedMessages: ChatMessageWithRecommendations[] = [];
    
    conversationHistory.forEach(msg => {
      // Add the original message
      syncedMessages.push({
        ...msg,
        recommendations: []
      });
      
      // If this message has recommendations, create separate messages for each recommendation
      if ((msg as any).recommendations && (msg as any).recommendations.length > 0) {
        (msg as any).recommendations.forEach((rec: any) => {
          syncedMessages.push({
            role: 'assistant',
            content: '', // Empty content - just show the recommendation card
            timestamp: new Date().toISOString(),
            recommendations: [rec]
          });
        });
      }
    });

    setMessagesWithRecommendations(prev => {
      const recommendationOnly = prev.filter(msg => msg.isRecommendation);
      const recommendationMap = new Map<string | null, ChatMessageWithRecommendations[]>();

      recommendationOnly.forEach(rec => {
        const key = rec.anchorTimestamp ?? null;
        const existing = recommendationMap.get(key) ?? [];
        existing.push({ ...rec });
        recommendationMap.set(key, existing);
      });

      const rebuilt: ChatMessageWithRecommendations[] = [];

      syncedMessages.forEach(msg => {
        rebuilt.push(msg);
        const key = msg.timestamp ?? null;
        if (recommendationMap.has(key)) {
          rebuilt.push(...(recommendationMap.get(key) ?? []));
          recommendationMap.delete(key);
        }
      });

      // Append any remaining recommendation groups without anchors or unmatched anchors
      recommendationMap.forEach(group => {
        rebuilt.push(...group);
      });

      return rebuilt;
    });
    
    // Scroll to bottom when messages are synced (including initial message)
    // Use requestAnimationFrame to ensure DOM is updated before scrolling
    if (syncedMessages.length > 0) {
      requestAnimationFrame(() => {
        setTimeout(() => scrollToBottom(), 50);
      });
    }
  }, [conversationHistory]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim() || isLoading) return;

    const userMessage: ChatMessageWithRecommendations = {
      role: 'user',
      content: message.trim(),
      timestamp: new Date().toISOString(),
      recommendations: []
    };

    onNewMessage(userMessage as ChatMessage);
    setMessagesWithRecommendations(prev => [...prev, userMessage]);
    setMessage('');
    setIsLoading(true);
    setExtractionSummary(null);
    setCurrentStatus('');

    try {
      // Detect if this is the first user message (initial response to welcome message)
      // Check if conversationHistory only has the initial agent message or is empty
      const hasOnlyInitialMessage = conversationHistory.length === 1 && 
        conversationHistory[0]?.role === 'assistant' &&
        conversationHistory[0]?.content?.includes('What city, state, or zip code');
      const isInitialResponse = conversationHistory.length === 0 || hasOnlyInitialMessage;
      
      const request: ChatRequest = {
        message: message.trim(),
        conversation_history: conversationHistory,
        llm_provider: llmProvider,
        is_initial_response: isInitialResponse,
        user_id: userId,
        conversation_id: conversationId
      };

      await dataService.chatStream(
        request,
        // onStatus
        (status: string) => {
          setCurrentStatus(status);
        },
        // onMessage
        (messageContent: string, metadata?: any) => {
          // Create the main message without recommendations (they're separate now)
          const assistantTimestamp = new Date().toISOString();
          const assistantMessage: ChatMessageWithRecommendations = {
            role: 'assistant',
            content: messageContent,
            timestamp: assistantTimestamp,
            recommendations: []
          };

          lastAssistantMessageTimestampRef.current = assistantTimestamp;
          
          // Add to conversation history immediately
          onNewMessage(assistantMessage as ChatMessage);
          setMessagesWithRecommendations(prev => [...prev, assistantMessage]);
          
          // Clear the streaming state to prevent re-rendering
          
          // Check if trial exceeded
          if (metadata?.trial_exceeded) {
            onTrialExceeded();
          }

          // Update conversation ID if it changed (new conversation)
          if (metadata?.conversation_id && metadata.conversation_id !== conversationId) {
            console.log('Conversation ID updated:', metadata.conversation_id);
            localStorage.setItem('current_conversation_id', metadata.conversation_id);
          }
          
          // Set extraction summary if available
          if (metadata?.extraction_summary) {
            setExtractionSummary(metadata.extraction_summary);
          }
          
        },
        // onRecommendation
        (recommendation: any) => {
          // Create a separate message for each recommendation
          const recommendationMessage: ChatMessageWithRecommendations = {
            role: 'assistant',
            content: undefined, // Use undefined for cleaner detection of recommendation-only messages
            timestamp: new Date().toISOString(),
            recommendations: [recommendation],
            isRecommendation: true,
            anchorTimestamp: lastAssistantMessageTimestampRef.current
          };
          
          // Add to local UI state for rendering (don't add to conversation history)
          setMessagesWithRecommendations(prev => [...prev, recommendationMessage]);
          
          // Update recommendations tracking
          onRecommendations([recommendation]);
        },
        // onError
        (error: string) => {
          console.error('Streaming error:', error);
          const errorMessage: ChatMessage = {
            role: 'assistant',
            content: `Sorry, I encountered an error: ${error}`,
            timestamp: new Date().toISOString()
          };
          onNewMessage(errorMessage);
        },
        // onDone
        () => {
          // Clear loading state and reset streaming state
          setIsLoading(false);
          setCurrentStatus('');
          setExtractionSummary(null);
        }
      );
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date().toISOString()
      };
      onNewMessage(errorMessage);
      setIsLoading(false);
      setCurrentStatus('');
      setExtractionSummary(null);
    }
  };


  // Hidden for now - hasRecommendations and handleRefresh function
  // const hasRecommendations = messagesWithRecommendations.some(
  //   msg => msg.recommendations && msg.recommendations.length > 0
  // );

  // const handleRefresh = async () => {
  //   if (!hasRecommendations || isLoading) return;

  //   // Find the last user message with recommendations
  //   const lastUserMessage = messagesWithRecommendations
  //     .slice()
  //     .reverse()
  //     .find(msg => msg.role === 'user' && msg.content);

  //   if (!lastUserMessage || !lastUserMessage.content) return;

  //   // Clear existing recommendations
  //   setMessagesWithRecommendations(prev => 
  //     prev.filter(msg => !msg.recommendations || msg.recommendations.length === 0)
  //   );

  //   // Re-trigger the chat request
  //   setIsLoading(true);
  //   setCurrentStatus('Refreshing recommendations...');

  //   try {
  //     const request: ChatRequest = {
  //       message: lastUserMessage.content,
  //       conversation_history: conversationHistory,
  //       llm_provider: llmProvider,
  //       is_initial_response: false,
  //       user_id: userId,
  //       conversation_id: conversationId
  //     };

  //     await dataService.chatStream(
  //       request,
  //       (status: string) => setCurrentStatus(status),
  //       (messageContent: string, metadata?: any) => {
  //         const assistantMessage: ChatMessageWithRecommendations = {
  //           role: 'assistant',
  //           content: messageContent,
  //           timestamp: new Date().toISOString(),
  //           recommendations: []
  //         };
          
  //         onNewMessage(assistantMessage as ChatMessage);
  //         setMessagesWithRecommendations(prev => [...prev, assistantMessage]);
          
  //         if (metadata?.trial_exceeded) {
  //           onTrialExceeded();
  //         }
  //         if (metadata?.conversation_id && metadata.conversation_id !== conversationId) {
  //           localStorage.setItem('current_conversation_id', metadata.conversation_id);
  //         }
  //       },
  //       (recommendation: any) => {
  //         const recommendationMessage: ChatMessageWithRecommendations = {
  //           role: 'assistant',
  //           content: undefined,
  //           timestamp: new Date().toISOString(),
  //           recommendations: [recommendation]
  //         };
          
  //         setMessagesWithRecommendations(prev => [...prev, recommendationMessage]);
  //         onRecommendations([recommendation]);
  //       },
  //       (error: string) => {
  //         console.error('Refresh error:', error);
  //         const errorMessage: ChatMessage = {
  //           role: 'assistant',
  //           content: `Sorry, I encountered an error refreshing: ${error}`,
  //           timestamp: new Date().toISOString()
  //         };
  //         onNewMessage(errorMessage);
  //       },
  //       () => {
  //         setIsLoading(false);
  //         setCurrentStatus('');
  //       }
  //     );
  //   } catch (error) {
  //     console.error('Error refreshing:', error);
  //     setIsLoading(false);
  //     setCurrentStatus('');
  //   }
  // };

  return (
    <div className="flex flex-col h-full bg-[#FCFBF9]">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="space-y-4">
          {messagesWithRecommendations.map((msg, index) => {
          // Check if this message has meaningful content (not just whitespace)
          const hasContent = msg.content && msg.content.trim() !== '';
          // Check if this is a recommendation-only message (no meaningful content, only recommendations)
          const isRecommendationOnly = !hasContent && msg.recommendations && msg.recommendations.length > 0;

          // Skip completely empty assistant messages that aren't recommendation-only
          if (msg.role === 'assistant' && !hasContent && (!msg.recommendations || msg.recommendations.length === 0)) {
            return null;
          }
          
          return (
            <div key={index}>
              {msg.role === 'user' ? (
                /* User Message - Right Aligned */
                <div className="flex justify-end gap-2 items-start">
                  <div className="rounded-xl rounded-tr-sm px-4 py-3 max-w-[80%] border shadow-sm" style={{ backgroundColor: '#E9E6DF', borderColor: '#EDEBE6' }}>
                    <p className="text-[15px]" style={{ color: '#221A13' }}>{msg.content}</p>
                  </div>
                  {/* User Avatar */}
                  <div className="w-11 h-11 rounded-full flex-shrink-0 flex items-center justify-center mt-1 overflow-hidden p-1 border-0" style={{ backgroundColor: '#E9E6DF' }}>
                    <ImageWithFallback src={userAvatarImg} alt="User" className="w-3/4 h-3/4 object-cover rounded-full" />
                  </div>
                </div>
              ) : isRecommendationOnly ? (
                /* Recommendation-only message - show cards horizontally */
                <div className="flex gap-2 items-start">
                  <div className="w-11 h-11 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    {/* Event Cards - Horizontal Scroll */}
                    <div className="flex gap-3 overflow-x-auto overflow-y-hidden scrollbar-hide horizontal-scroll-mobile pb-2">
                      {msg.recommendations?.map((rec, recIndex) => (
                        <div key={recIndex} className="flex-none flex-shrink-0">
                          <RecommendationCard recommendation={rec} />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                /* Bot Response with optional Cards */
                <div className="flex gap-2 items-start">
                  {/* Bot Avatar */}
                  <div className="w-11 h-11 rounded-full flex-shrink-0 flex items-center justify-center mt-1 overflow-hidden p-1.5 border-2" style={{ backgroundColor: 'white', borderColor: 'rgba(118, 193, 178, 0.6)' }}>
                    <ImageWithFallback src={agentAvatarImg} alt="Agent" className="w-4/5 h-4/5 object-cover" />
                  </div>
                  
                  {/* Bot Message */}
                  <div className="flex-1 min-w-0">
                    <div className="bg-white rounded-xl rounded-tl-sm px-4 py-3 shadow-md border mb-3" style={{ borderColor: '#F5F5F5' }}>
                      <p className="text-[15px]" style={{ color: '#221A13' }}>{msg.content}</p>
                    </div>

                    {/* Event Cards - Horizontal Scroll */}
                    {msg.recommendations && msg.recommendations.length > 0 && (
                      <div className="flex gap-3 overflow-x-auto overflow-y-hidden scrollbar-hide horizontal-scroll-mobile pb-2">
                        {msg.recommendations.map((rec, recIndex) => (
                          <div key={recIndex} className="flex-none flex-shrink-0">
                            <RecommendationCard recommendation={rec} />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
        
        {isLoading && (
          <div className="flex gap-2 items-start">
            {/* Bot Avatar */}
            <div className="w-11 h-11 rounded-full flex-shrink-0 flex items-center justify-center mt-1 overflow-hidden p-1.5 border-2" style={{ backgroundColor: 'white', borderColor: 'rgba(118, 193, 178, 0.6)' }}>
              <ImageWithFallback src={agentAvatarImg} alt="Agent" className="w-4/5 h-4/5 object-cover" />
            </div>
            
            {/* Loading Message */}
            <div className="bg-white rounded-xl rounded-tl-sm px-4 py-3 shadow-md border" style={{ borderColor: '#F5F5F5' }}>
              <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" style={{ color: '#76C1B2' }} />
                <p className="text-[15px]" style={{ color: '#221A13' }}>
                  {currentStatus || extractionSummary || ''}
                </p>
              </div>
            </div>
          </div>
        )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="bg-[#FCFBF9] px-4 py-6 flex-shrink-0">
        <form onSubmit={handleSubmit} className="flex gap-3 items-center relative">
          {/* Refresh Button - Hidden for now */}
          {/* <div className="relative">
            <button
              type="button"
              onClick={handleRefresh}
              disabled={!hasRecommendations || isLoading}
              className="rounded-full bg-white h-14 w-14 flex items-center justify-center transition-all shadow-md border-[0.5px] border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 disabled:hover:bg-white active:scale-90 active:shadow-lg"
            >
              <img 
                src={refreshIcon} 
                alt="Refresh" 
                className="w-8 h-8 transition-transform active:rotate-180" 
                style={{ 
                  filter: 'invert(67%) sepia(18%) saturate(1245%) hue-rotate(121deg) brightness(92%) contrast(86%)'
                }} 
              />
            </button>
          </div> */}
          
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={messagesWithRecommendations.length > 0 ? "What else are you looking for?" : "City, State/ City name/Zipcode"}
            className="flex-1 rounded-xl border-[0.5px] border-slate-200 bg-white shadow-md h-14 text-base px-6 placeholder:text-[#5E574E] focus:outline-none focus:ring-2 focus:ring-[#76C1B2]/50"
            style={{ color: '#221A13' }}
            disabled={isLoading}
          />
          
          <button
            type="submit"
            disabled={!message.trim() || isLoading}
            className="rounded-full bg-white hover:bg-slate-50 h-14 w-14 flex items-center justify-center transition-all shadow-md border-[0.5px] border-slate-200 active:scale-90 active:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <Loader2 className="w-7 h-7 animate-spin" style={{ color: '#B46A55' }} />
            ) : (
              <Send className="w-7 h-7" style={{ color: '#B46A55' }} />
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

export default ChatInterface;

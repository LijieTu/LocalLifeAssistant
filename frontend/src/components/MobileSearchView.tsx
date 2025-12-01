import { useState, useEffect, useRef } from 'react';
import { Input } from './ui/input';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from './ui/sheet';
import {
  Send,
  MapPin,
  Menu,
  Home,
  LogIn,
  UserPlus,
  Sparkles,
  MessageSquare,
  Music2,
  Dumbbell,
  Wine,
  Briefcase,
  Cpu,
  Heart
} from 'lucide-react';
import { ChatMessage, ChatRequest, apiClient } from '../api/client';
import { dataService } from '../services/dataService';
import RecommendationCard from './RecommendationCard';
import DancingPet from './DancingPet';
import userAvatar from '../assets/images/figma/user-avatar.png';
import agentAvatar from '../assets/images/figma/agent-avatar.png';
import musicIcon from '../assets/images/figma/music-icon.png';
import wellnessIcon from '../assets/images/figma/wellness-icon.png';
import luckyIcon from '../assets/images/figma/lucky-icon.png';
import tapIcon from '../assets/images/figma/tap-icon.png';
import catGif from '../assets/images/cat-sunglasses.gif';
import { User } from 'firebase/auth';


interface ChatMessageWithRecommendations extends ChatMessage {
  showEvents?: boolean;
  showCitySelection?: boolean;
  showEventTypeSelection?: boolean;
  showFollowUpSuggestions?: boolean;
  recommendations?: any[];
}

interface MobileSearchViewProps {
  onNewMessage: (message: ChatMessage) => void;
  onRecommendations: (recommendations: any[]) => void;
  llmProvider: string;
  conversationHistory: ChatMessage[];
  userId: string;
  onTrialExceeded: () => void;
  conversationId: string | null;
  currentUser: User | null;
  authLoading: boolean;
  usageStats: any;
  trialWarning: string;
  onLogin: () => void;
  onRegister: () => void;
  onLogout: () => void;
}

// Helper function to convert snake_case to Title Case
const snakeToTitleCase = (str: string): string => {
  return str
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
};


// Follow-up suggestions after showing events
const getFollowUpSuggestions = (eventType: string) => {
  const followUpSuggestions: Record<string, Array<{text: string, label: string}>> = {
    'music': [
      { text: 'Show me jazz events', label: 'saxophone' },
      { text: 'Find classical concerts', label: 'violin' },
      { text: 'Live bands tonight', label: 'guitar' }
    ],
    'sports': [
      { text: 'Marathon events', label: 'marathon' },
      { text: 'Rock climbing gyms', label: 'climbing' },
      { text: 'Cycling groups', label: 'cycling' }
    ],
    'nightlife': [
      { text: 'Rooftop bars', label: 'rooftop' },
      { text: 'DJ events tonight', label: 'dj' },
      { text: 'Late-night comedy', label: 'comedy' }
    ],
    'business': [
      { text: 'Networking events', label: 'networking' },
      { text: 'Business conferences', label: 'conference' },
      { text: 'Professional workshops', label: 'workshop' }
    ],
    'tech': [
      { text: 'AI & ML meetups', label: 'ai' },
      { text: 'Web3 conferences', label: 'web3' },
      { text: 'Developer workshops', label: 'dev' }
    ],
    'dating': [
      { text: 'Speed dating events', label: 'speed' },
      { text: 'Social mixers', label: 'mixer' },
      { text: 'Singles activities', label: 'singles' }
    ]
  };
  
  return followUpSuggestions[eventType] || [
    { text: 'Show me more options', label: 'more' },
    { text: 'Find similar events', label: 'similar' },
    { text: 'What else is nearby?', label: 'nearby' }
  ];
};

// Initial example questions for users
const initialExamples = [
  { text: 'Show me live music this weekend', icon: musicIcon },
  { text: 'Find wellness activities near me', icon: wellnessIcon },
  { text: 'Surprise me with something fun!', icon: luckyIcon },
  { text: 'What\'s happening tonight?', icon: tapIcon }
];



export function MobileSearchView({
  onNewMessage,
  onRecommendations,
  llmProvider,
  conversationHistory,
  userId,
  onTrialExceeded,
  conversationId,
  currentUser,
  authLoading,
  usageStats,
  trialWarning,
  onLogin,
  onRegister,
  onLogout
}: MobileSearchViewProps) {
  const [query, setQuery] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [userProfilePic] = useState(userAvatar);
  const [selectedCityIndex, setSelectedCityIndex] = useState(-1); // Not selected yet
  const [selectedEventTypeIndex, setSelectedEventTypeIndex] = useState(-1); // Not selected yet
  const [hasCompletedInitialSelection, setHasCompletedInitialSelection] = useState(false);
  const [showLocationDropdown, setShowLocationDropdown] = useState(false);
  const [showEventTypeDropdown, setShowEventTypeDropdown] = useState(false);
  const [supportedCities, setSupportedCities] = useState<string[]>([]);
  const [citiesDisplay, setCitiesDisplay] = useState<string[]>([]);
  const [supportedEventTypes, setSupportedEventTypes] = useState<string[]>([]);
  const [messagesWithRecommendations, setMessagesWithRecommendations] = useState<ChatMessageWithRecommendations[]>([]);
  const lastUserMessageRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const initialViewportHeight = useRef<number>(0);
  const shouldAutoScroll = useRef(true);
  const currentAssistantMessageIndexRef = useRef<number>(-1);

  // Start with bot asking for city selection
  const [messages, setMessages] = useState<ChatMessageWithRecommendations[]>([
    {
      role: 'assistant',
      content: 'Where are you looking for events?',
      showCitySelection: true,
    }
  ]);

  // Find the index of the last user message
  const lastUserMessageIndex = messages.map((msg, i) => msg.role === 'user' ? i : -1).filter(i => i !== -1).pop() ?? -1;

  // Load real cities and event types from API
  useEffect(() => {
    const loadCities = async () => {
      try {
        const citiesSnakeCase = await apiClient.getSupportedCities();
        setSupportedCities(citiesSnakeCase);
        // Convert to Title Case for display
        const citiesTitleCase = citiesSnakeCase.map(city => snakeToTitleCase(city));
        setCitiesDisplay(citiesTitleCase);
      } catch (error) {
        console.error('Error loading supported cities:', error);
        const fallbackCities = ['san_francisco', 'new_york', 'los_angeles', 'miami', 'chicago', 'seattle', 'boston'];
        setSupportedCities(fallbackCities);
        setCitiesDisplay(fallbackCities.map(city => snakeToTitleCase(city)));
      }
    };
    
    const loadEventTypes = async () => {
      try {
        const eventTypes = await apiClient.getSupportedEventTypes();
        setSupportedEventTypes(eventTypes);
      } catch (error) {
        console.error('Error loading supported event types:', error);
        setSupportedEventTypes(['music', 'sports', 'nightlife', 'business', 'tech', 'dating']);
      }
    };
    
    loadCities();
    loadEventTypes();
  }, []);

  // Initialize from conversationHistory on mount
  useEffect(() => {
    if (messagesWithRecommendations.length === 0 && conversationHistory.length > 0) {
      const conversationMessages: ChatMessageWithRecommendations[] = conversationHistory.map(msg => {
        const recommendations = (msg as any).recommendations ?? [];
        return {
          ...msg,
          recommendations: recommendations,
          showEvents: recommendations.length > 0
        };
      });
      setMessagesWithRecommendations(conversationMessages);
      setMessages(conversationMessages);
    }
  }, []);

  // Detect keyboard open/close on mobile
  useEffect(() => {
    if (typeof window === 'undefined') return;
    
    // Store initial viewport height
    initialViewportHeight.current = window.innerHeight;
    
    const handleResize = () => {
      // Keyboard detection logic removed since we no longer need it
    };
    
    window.addEventListener('resize', handleResize);
    
    // Also listen to visualViewport if available (better for mobile keyboards)
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', handleResize);
    }
    
    return () => {
      window.removeEventListener('resize', handleResize);
      if (window.visualViewport) {
        window.visualViewport.removeEventListener('resize', handleResize);
      }
    };
  }, []);

  // Scroll the latest user message to the top of the chat window
  useEffect(() => {
    if (lastUserMessageRef.current && shouldAutoScroll.current) {
      // Use a small delay to ensure DOM is updated
      setTimeout(() => {
        lastUserMessageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 50);
    }
  }, [messages, isTyping]);

  // Auto-focus input after initial message
  useEffect(() => {
    if (!isTyping) {
      // Focus after initial bot message
      if (messages.length === 1 && messages[0].role === 'assistant') {
        setTimeout(() => {
          inputRef.current?.focus();
        }, 300);
      }
    }
  }, [isTyping, messages.length]);

  // Helper function to normalize city names for matching
  const normalizeCityForMatch = (city: string): string => {
    return city.toLowerCase().replace(/\s+/g, '_');
  };

  // Helper function to detect if input "looks like" a city or event type
  const looksLikeCity = (input: string): boolean => {
    // If it's a single word or two words in Title Case, it might be a city
    const words = input.trim().split(/\s+/);
    if (words.length <= 2) {
      const cityPatterns = [
        /\b(new|san|los|las|saint|st\.)\s+\w+/i,
        /^[A-Z][a-z]+(\s+[A-Z][a-z]+)?$/, // Title Case (e.g., "New York" or "Boston")
      ];
      if (cityPatterns.some(pattern => pattern.test(input))) {
        return true;
      }
    }
    // Check if it's similar to any supported city name
    return citiesDisplay.some(city => {
      const cityLower = city.toLowerCase();
      const inputLower = input.toLowerCase();
      return cityLower.includes(inputLower) || inputLower.includes(cityLower) || 
             normalizeCityForMatch(city) === normalizeCityForMatch(input);
    });
  };

  const looksLikeEventType = (input: string): boolean => {
    const inputLower = input.toLowerCase().trim();
    const inputWords = inputLower.split(/\s+/);
    
    // Check if any word in the input matches a supported event type
    if (supportedEventTypes.some(type => inputWords.includes(type.toLowerCase()))) {
      return true;
    }
    
    // Check if input contains event-related keywords
    const eventKeywords = ['music', 'sports', 'nightlife', 'business', 'tech', 'dating', 'concert', 'event', 'show', 'meetup', 'conference', 'workshop', 'festival', 'party', 'networking', 'comedy', 'theater'];
    return eventKeywords.some(keyword => inputWords.includes(keyword) || inputLower.includes(keyword));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isTyping) return;

    inputRef.current?.blur();

    const inputText = query.trim();
    const inputLower = inputText.toLowerCase();
    
    // Create and add user message IMMEDIATELY before any processing
    // This ensures the user sees their input right away
    const userMessage: ChatMessageWithRecommendations = {
      role: 'user',
      content: inputText,
      timestamp: new Date().toISOString(),
      recommendations: []
    };
    
    // Add to chat immediately (synchronously)
    // This ensures the user sees their input right away
    onNewMessage(userMessage as ChatMessage);
    setMessages(prev => [...prev, userMessage]);
    setMessagesWithRecommendations(prev => [...prev, userMessage]);
    setQuery(''); // Clear input immediately so user sees it was submitted
    
    // Use setTimeout(0) to defer processing to next event loop tick
    // This allows React to render the user message immediately while processing happens in parallel
    // We pass inputText and inputLower to avoid closure issues with the cleared query state
    setTimeout(() => {
      processUserInput(inputText, inputLower);
    }, 0);
    
    return;
  };
  
  const processUserInput = async (inputText: string, inputLower: string) => {
    
    // Extract keywords from input (split by spaces and common separators)
    const inputWords = inputLower.split(/\s+/).filter(word => word.length > 0);
    
    // Helper function to find city in input (exact match or keyword extraction)
    const findCityInInput = (): number => {
      // First try exact match
      let index = citiesDisplay.findIndex(city => 
        city.toLowerCase() === inputLower || 
        normalizeCityForMatch(city) === normalizeCityForMatch(inputText)
      );
      if (index >= 0) return index;
      
      // Then try to find city name as a keyword in the input
      for (let i = 0; i < citiesDisplay.length; i++) {
        const cityLower = citiesDisplay[i].toLowerCase();
        const cityWords = cityLower.split(/\s+/);
        
        // Check if all words of city name appear in input (e.g., "New York" in "i want new york")
        if (cityWords.every(word => inputWords.includes(word))) {
          return i;
        }
        
        // For single-word cities, check if the city name appears as a word in input
        // (e.g., "seattle" in "i want seattle")
        if (cityWords.length === 1 && inputWords.includes(cityWords[0])) {
          return i;
        }
        
        // Also check normalized version (handles snake_case cities)
        const cityNormalized = normalizeCityForMatch(citiesDisplay[i]);
        const cityNormalizedWords = cityNormalized.split('_');
        if (cityNormalizedWords.every(word => inputWords.includes(word))) {
          return i;
        }
        
        // Check if any input word matches the normalized city
        if (inputWords.some(word => normalizeCityForMatch(word) === cityNormalized)) {
          return i;
        }
      }
      return -1;
    };

    // Helper function to find event type in input (exact match or keyword extraction)
    const findEventTypeInInput = (): number => {
      // First try exact match
      let index = supportedEventTypes.findIndex(type => 
        type.toLowerCase() === inputLower
      );
      if (index >= 0) return index;
      
      // Then try to find event type as a keyword in the input
      for (let i = 0; i < supportedEventTypes.length; i++) {
        const typeLower = supportedEventTypes[i].toLowerCase();
        // Check if event type appears as a word in the input
        if (inputWords.includes(typeLower)) {
          return i;
        }
        // Also check if input contains the event type as a substring
        if (inputLower.includes(typeLower)) {
          return i;
        }
      }
      return -1;
    };

    const matchedCityIndex = findCityInInput();
    const matchedEventTypeIndex = findEventTypeInInput();

    // Handle valid city input
    if (matchedCityIndex >= 0) {
      setSelectedCityIndex(matchedCityIndex);
      setIsTyping(true);
      
      // Bot asks for event type
      setTimeout(() => {
        const botMessage: ChatMessageWithRecommendations = {
          role: 'assistant',
          content: 'What kind of events are you interested in?',
          showEventTypeSelection: true,
        };
        setMessages(prev => [...prev, botMessage]);
        setIsTyping(false);
      }, 800);
      return;
    }

    // Handle valid event type input
    if (matchedEventTypeIndex >= 0) {
      setSelectedEventTypeIndex(matchedEventTypeIndex);
      
      // If city is already selected, trigger API call
      if (selectedCityIndex >= 0) {
        setHasCompletedInitialSelection(true);
        setIsTyping(true);
        currentAssistantMessageIndexRef.current = -1;

        // Trigger API call with new event type
        const citySnakeCase = supportedCities[selectedCityIndex];
        const eventType = supportedEventTypes[matchedEventTypeIndex];
        const messageToSend = `${citySnakeCase}:${eventType}: Show me ${eventType} events in ${citiesDisplay[selectedCityIndex]}`;

        try {
          const request: ChatRequest = {
            message: messageToSend,
            conversation_history: conversationHistory,
            llm_provider: llmProvider,
            is_initial_response: conversationHistory.length <= 1,
            user_id: userId,
            conversation_id: conversationId
          };

          let recommendationCount = 0;
          let botMessage: ChatMessageWithRecommendations | null = null;

          await dataService.chatStream(
            request,
            () => {},
            (messageContent: string, metadata?: any) => {
              console.log('📨 [handleSubmit] Received message:', messageContent);
              
              if (metadata?.trial_exceeded) {
                onTrialExceeded();
              }
              if (metadata?.conversation_id && metadata.conversation_id !== conversationId) {
                localStorage.setItem('current_conversation_id', metadata.conversation_id);
              }
            },
            (recommendation: any) => {
              const recTitle = recommendation?.data?.title || recommendation?.data?.data?.title || 'Unknown';
              console.log('📥 [handleSubmit] Received recommendation:', recTitle);
              
              recommendationCount++;
              
              if (!botMessage) {
                botMessage = {
                  role: 'assistant',
                  content: `Found ${recommendationCount} events in ${citiesDisplay[selectedCityIndex]} that match your search! Check out the recommendations ↓`,
                  timestamp: new Date().toISOString(),
                  recommendations: [recommendation],
                  showEvents: true
                };
                
                setMessages(prev => [...prev, botMessage!]);
                setMessagesWithRecommendations(prev => [...prev, botMessage!]);
                currentAssistantMessageIndexRef.current = -1;
                setIsTyping(false);
              } else {
                botMessage = {
                  ...botMessage,
                  content: `Found ${recommendationCount} events in ${citiesDisplay[selectedCityIndex]} that match your search! Check out the recommendations ↓`,
                  recommendations: [...(botMessage.recommendations || []), recommendation]
                };
                
                setMessages(prev => {
                  const updated = [...prev];
                  if (currentAssistantMessageIndexRef.current >= 0 && currentAssistantMessageIndexRef.current < updated.length) {
                    updated[currentAssistantMessageIndexRef.current] = botMessage!;
                  }
                  return updated;
                });
                
                setMessagesWithRecommendations(prev => {
                  const updated = [...prev];
                  if (currentAssistantMessageIndexRef.current >= 0 && currentAssistantMessageIndexRef.current < updated.length) {
                    updated[currentAssistantMessageIndexRef.current] = botMessage!;
                  }
                  return updated;
                });
              }
              
              onRecommendations([recommendation]);
            },
            (error: string) => {
              console.error('Streaming error:', error);
              const errorMessage: ChatMessage = {
                role: 'assistant',
                content: `Sorry, I encountered an error: ${error}`,
                timestamp: new Date().toISOString()
              };
              onNewMessage(errorMessage);
              setIsTyping(false);
            },
            () => {
              setIsTyping(false);
            }
          );
        } catch (error) {
          console.error('Error in handleSubmit:', error);
          setIsTyping(false);
        }
        return;
      } else {
        // City not selected, ask for city first
        const errorMessage: ChatMessageWithRecommendations = {
          role: 'assistant',
          content: 'Please select a city first, then choose an event type.',
          timestamp: new Date().toISOString(),
        };
        setMessages(prev => [...prev, errorMessage]);
        setMessagesWithRecommendations(prev => [...prev, errorMessage]);
        return;
      }
    }

    // Handle invalid input that looks like city or event type
    if (looksLikeCity(inputText) && matchedCityIndex < 0) {
      const errorMessage: ChatMessageWithRecommendations = {
        role: 'assistant',
        content: 'This city is not supported. Please either re-enter the correct name or use the button to select.',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMessage]);
      setMessagesWithRecommendations(prev => [...prev, errorMessage]);
      return;
    }

    if (looksLikeEventType(inputText) && matchedEventTypeIndex < 0) {
      const errorMessage: ChatMessageWithRecommendations = {
        role: 'assistant',
        content: 'This event type is not supported. Please either re-enter the correct name or use the button to select.',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMessage]);
      setMessagesWithRecommendations(prev => [...prev, errorMessage]);
      return;
    }

    // Regular query - check if it contains a different event type and update state
    // Include selected city and event type in message if available (send snake_case format)
    let messageToSend = inputText;
    let eventTypeToUse = selectedEventTypeIndex >= 0 ? supportedEventTypes[selectedEventTypeIndex] : null;
    
    // Check if query contains a different event type (extract keywords)
    if (hasCompletedInitialSelection && selectedEventTypeIndex >= 0) {
      const queryLower = inputText.toLowerCase();
      const queryWords = queryLower.split(/\s+/);
      
      for (let i = 0; i < supportedEventTypes.length; i++) {
        const typeLower = supportedEventTypes[i].toLowerCase();
        const currentTypeLower = supportedEventTypes[selectedEventTypeIndex].toLowerCase();
        
        // Check if event type appears as a word in the query
        if (typeLower !== currentTypeLower && queryWords.includes(typeLower)) {
          // Found a different event type as a word in the query - update state
          setSelectedEventTypeIndex(i);
          eventTypeToUse = supportedEventTypes[i];
          break;
        }
        // Also check as substring if not found as word
        if (typeLower !== currentTypeLower && queryLower.includes(typeLower) && !eventTypeToUse) {
          setSelectedEventTypeIndex(i);
          eventTypeToUse = supportedEventTypes[i];
          break;
        }
      }
    }
    
    if (hasCompletedInitialSelection && supportedCities[selectedCityIndex] && eventTypeToUse) {
      const citySnakeCase = supportedCities[selectedCityIndex];
      messageToSend = `${citySnakeCase}:${eventTypeToUse}: ${inputText}`;
    }

    // User message was already added at the start of handleSubmit
    setIsTyping(true);
    currentAssistantMessageIndexRef.current = -1;

    try {
      const request: ChatRequest = {
        message: messageToSend,
        conversation_history: conversationHistory,
        llm_provider: llmProvider,
        is_initial_response: conversationHistory.length <= 1,
        user_id: userId,
        conversation_id: conversationId
      };

      await dataService.chatStream(
        request,
        () => {},
        (messageContent: string, metadata?: any) => {
          console.log('📨 [handleSubmit] Received message:', messageContent);
          setMessages(prev => {
            let targetIndex = currentAssistantMessageIndexRef.current;
            
            if (targetIndex < 0 || targetIndex >= prev.length || prev[targetIndex].role !== 'assistant') {
              for (let i = prev.length - 1; i >= 0; i--) {
                if (prev[i].role === 'assistant') {
                  targetIndex = i;
                  break;
                }
              }
            }
            
            if (targetIndex >= 0 && targetIndex < prev.length && prev[targetIndex]) {
              const targetMessage = prev[targetIndex];
              const existingRecommendations = targetMessage.recommendations || [];
              const updatedMessages = [...prev];
              updatedMessages[targetIndex] = {
                ...targetMessage,
                content: messageContent,
                recommendations: existingRecommendations,
                showEvents: true
              };
              currentAssistantMessageIndexRef.current = targetIndex;
              return updatedMessages;
            } else {
              const assistantMessage: ChatMessageWithRecommendations = {
                role: 'assistant',
                content: messageContent,
                timestamp: new Date().toISOString(),
                recommendations: [],
                showEvents: false
              };
              const newIndex = prev.length;
              currentAssistantMessageIndexRef.current = newIndex;
              return [...prev, assistantMessage];
            }
          });
          
          setMessagesWithRecommendations(prev => {
            let targetIndex = currentAssistantMessageIndexRef.current;
            
            if (targetIndex < 0 || targetIndex >= prev.length || prev[targetIndex].role !== 'assistant') {
              for (let i = prev.length - 1; i >= 0; i--) {
                if (prev[i].role === 'assistant') {
                  targetIndex = i;
                  break;
                }
              }
            }
            
            if (targetIndex >= 0 && targetIndex < prev.length && prev[targetIndex]) {
              const targetMessage = prev[targetIndex];
              const existingRecommendations = targetMessage.recommendations || [];
              const updatedMessages = [...prev];
              updatedMessages[targetIndex] = {
                ...targetMessage,
                content: messageContent,
                recommendations: existingRecommendations,
                showEvents: true
              };
              return updatedMessages;
            } else {
              const assistantMessage: ChatMessageWithRecommendations = {
                role: 'assistant',
                content: messageContent,
                timestamp: new Date().toISOString(),
                recommendations: [],
                showEvents: false
              };
              return [...prev, assistantMessage];
            }
          });
          
          
          if (metadata?.trial_exceeded) {
            onTrialExceeded();
          }
          if (metadata?.conversation_id && metadata.conversation_id !== conversationId) {
            localStorage.setItem('current_conversation_id', metadata.conversation_id);
          }
        },
        (recommendation: any) => {
          const recTitle = recommendation?.data?.title || recommendation?.data?.data?.title || 'Unknown';
          console.log('📥 [handleSubmit] Received recommendation:', recTitle);
          setMessages(prev => {
            const updatedMessages = [...prev];
            let targetIndex = currentAssistantMessageIndexRef.current;
            
            if (targetIndex < 0 || targetIndex >= updatedMessages.length || updatedMessages[targetIndex].role !== 'assistant') {
              const newIndex = updatedMessages.length;
              updatedMessages.push({
                role: 'assistant',
                content: '',
                timestamp: new Date().toISOString(),
                recommendations: [recommendation],
                showEvents: true
              });
              currentAssistantMessageIndexRef.current = newIndex;
              return updatedMessages;
            }

            const targetMessage = updatedMessages[targetIndex];
            const messageTime = targetMessage.timestamp ? new Date(targetMessage.timestamp).getTime() : 0;
            const now = Date.now();
            const isRecentMessage = (now - messageTime) < 10000;
            
            // Check for duplicate recommendation by event_id
            const recId = recommendation?.data?.event_id || recommendation?.data?.data?.event_id;
            const existingRecIds = (targetMessage.recommendations ?? []).map((r: any) => 
              r?.data?.event_id || r?.data?.data?.event_id
            );
            const isDuplicate = recId && existingRecIds.includes(recId);
            
            if (isRecentMessage && !isDuplicate) {
              const newRecommendations = [...(targetMessage.recommendations ?? []), recommendation];
              updatedMessages[targetIndex] = {
                ...targetMessage,
                recommendations: newRecommendations,
                showEvents: true
              };
            } else if (!isRecentMessage && !isDuplicate) {
              const newIndex = updatedMessages.length;
              updatedMessages.push({
                role: 'assistant',
                content: '',
                timestamp: new Date().toISOString(),
                recommendations: [recommendation],
                showEvents: true
              });
              currentAssistantMessageIndexRef.current = newIndex;
            } else if (isDuplicate) {
              // Skip duplicate recommendation
              console.log('Skipping duplicate recommendation:', recTitle);
              return updatedMessages;
            }

            return updatedMessages;
          });
          
          setMessagesWithRecommendations(prev => {
            const updatedMessages = [...prev];
            let targetIndex = currentAssistantMessageIndexRef.current;
            
            if (targetIndex < 0 || targetIndex >= updatedMessages.length || updatedMessages[targetIndex].role !== 'assistant') {
              const newIndex = updatedMessages.length;
              updatedMessages.push({
                role: 'assistant',
                content: '',
                timestamp: new Date().toISOString(),
                recommendations: [recommendation],
                showEvents: true
              });
              currentAssistantMessageIndexRef.current = newIndex;
              return updatedMessages;
            }

            const targetMessage = updatedMessages[targetIndex];
            const messageTime = targetMessage.timestamp ? new Date(targetMessage.timestamp).getTime() : 0;
            const now = Date.now();
            const isRecentMessage = (now - messageTime) < 10000;
            
            // Check for duplicate recommendation by event_id
            const recId = recommendation?.data?.event_id || recommendation?.data?.data?.event_id;
            const existingRecIds = (targetMessage.recommendations ?? []).map((r: any) => 
              r?.data?.event_id || r?.data?.data?.event_id
            );
            const isDuplicate = recId && existingRecIds.includes(recId);
            
            if (isRecentMessage && !isDuplicate) {
              const newRecommendations = [...(targetMessage.recommendations ?? []), recommendation];
              updatedMessages[targetIndex] = {
                ...targetMessage,
                recommendations: newRecommendations,
                showEvents: true
              };
            } else if (!isRecentMessage && !isDuplicate) {
              const newIndex = updatedMessages.length;
              updatedMessages.push({
                role: 'assistant',
                content: '',
                timestamp: new Date().toISOString(),
                recommendations: [recommendation],
                showEvents: true
              });
              currentAssistantMessageIndexRef.current = newIndex;
            } else if (isDuplicate) {
              // Skip duplicate recommendation
              console.log('Skipping duplicate recommendation:', recTitle);
              return updatedMessages;
            }

            return updatedMessages;
          });
          
          onRecommendations([recommendation]);
        },
        (error: string) => {
          console.error('Streaming error:', error);
          const errorMessage: ChatMessage = {
            role: 'assistant',
            content: `Sorry, I encountered an error: ${error}`,
            timestamp: new Date().toISOString()
          };
          onNewMessage(errorMessage);
        },
        () => {
          setIsTyping(false);
        }
      );
    } catch (error) {
      console.error('Error sending message:', error);
      setIsTyping(false);
    }
  };

  const handleSuggestionClick = async (suggestionText: string) => {
    if (isTyping) return;
    
    // Include selected city and event type in message if available (send snake_case format)
    let messageToSend = suggestionText;
    if (hasCompletedInitialSelection && supportedCities[selectedCityIndex] && supportedEventTypes[selectedEventTypeIndex]) {
      const citySnakeCase = supportedCities[selectedCityIndex];
      const eventType = supportedEventTypes[selectedEventTypeIndex];
      messageToSend = `${citySnakeCase}:${eventType}: ${suggestionText}`;
    }
    
    const userMessage: ChatMessageWithRecommendations = {
      role: 'user',
      content: suggestionText,
      timestamp: new Date().toISOString(),
      recommendations: []
    };

    onNewMessage(userMessage as ChatMessage);
    setMessages(prev => [...prev, userMessage]);
    setMessagesWithRecommendations(prev => [...prev, userMessage]);
    setIsTyping(true);
    currentAssistantMessageIndexRef.current = -1;

    // Same streaming logic as handleSubmit...
    try {
      const request: ChatRequest = {
        message: messageToSend,
        conversation_history: conversationHistory,
        llm_provider: llmProvider,
        is_initial_response: conversationHistory.length <= 1,
        user_id: userId,
        conversation_id: conversationId
      };

      let recommendationCount = 0;
      let botMessage: ChatMessageWithRecommendations | null = null;

      await dataService.chatStream(
        request,
        () => {},
        (messageContent: string, metadata?: any) => {
          // We'll handle the message creation when we get recommendations
          console.log('📨 [handleSuggestionClick] Received message:', messageContent);
          
          if (metadata?.trial_exceeded) {
            onTrialExceeded();
          }
          if (metadata?.conversation_id && metadata.conversation_id !== conversationId) {
            localStorage.setItem('current_conversation_id', metadata.conversation_id);
          }
        },
        (recommendation: any) => {
          const recTitle = recommendation?.data?.title || recommendation?.data?.data?.title || 'Unknown';
          console.log('📥 [handleSuggestionClick] Received recommendation:', recTitle);
          
          recommendationCount++;
          
          // Create or update the bot message with the specific text and recommendations
          if (!botMessage) {
            botMessage = {
              role: 'assistant',
              content: `Found ${recommendationCount} events in ${citiesDisplay[selectedCityIndex]} that match your search! Check out the recommendations ↓`,
              timestamp: new Date().toISOString(),
              recommendations: [recommendation],
              showEvents: true
            };
            
            setMessages(prev => [...prev, botMessage!]);
            setMessagesWithRecommendations(prev => [...prev, botMessage!]);
            currentAssistantMessageIndexRef.current = -1; // Reset since we created a new message
            
            // Stop typing indicator as soon as the main message appears
            setIsTyping(false);
          } else {
            // Update the existing message with more recommendations and updated count
            botMessage = {
              ...botMessage,
              content: `Found ${recommendationCount} events in ${citiesDisplay[selectedCityIndex]} that match your search! Check out the recommendations ↓`,
              recommendations: [...(botMessage.recommendations || []), recommendation]
            };
            
            setMessages(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = botMessage!;
              return updated;
            });
            
            setMessagesWithRecommendations(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = botMessage!;
              return updated;
            });
          }
          
          onRecommendations([recommendation]);
        },
        (error: string) => {
          console.error('Streaming error:', error);
          const errorMessage: ChatMessage = {
            role: 'assistant',
            content: `Sorry, I encountered an error: ${error}`,
            timestamp: new Date().toISOString()
          };
          onNewMessage(errorMessage);
        },
        () => {
          setIsTyping(false);
          
          // If we got recommendations, notify parent about the final message
          if (botMessage) {
            onNewMessage(botMessage as ChatMessage);
          }
        }
      );
    } catch (error) {
      console.error('Error sending suggestion:', error);
      setIsTyping(false);
    }
  };

  const handleCitySelect = (cityIndex: number) => {
    setSelectedCityIndex(cityIndex);
    
    // Add user message showing selected city
    const userMessage: ChatMessageWithRecommendations = {
      role: 'user',
      content: citiesDisplay[cityIndex],
      timestamp: new Date().toISOString(),
    };
    
    onNewMessage(userMessage as ChatMessage);
    setMessages(prev => [...prev, userMessage]);
    setIsTyping(true);
    
    // Bot asks for event type
    setTimeout(() => {
      const botMessage: ChatMessageWithRecommendations = {
        role: 'assistant',
        content: 'What kind of events are you interested in?',
        showEventTypeSelection: true,
      };
      setMessages(prev => [...prev, botMessage]);
      setIsTyping(false);
    }, 800);
  };

  const handleEventTypeSelect = async (typeIndex: number) => {
    setSelectedEventTypeIndex(typeIndex);
    setHasCompletedInitialSelection(true);
    
    // Add user message showing selected event type
    const userMessage: ChatMessageWithRecommendations = {
      role: 'user',
      content: supportedEventTypes[typeIndex],
      timestamp: new Date().toISOString(),
    };
    
    onNewMessage(userMessage as ChatMessage);
    setMessages(prev => [...prev, userMessage]);
    setMessagesWithRecommendations(prev => [...prev, userMessage]);
    setIsTyping(true);
    currentAssistantMessageIndexRef.current = -1;

    // Trigger actual API call to get recommendations
    const citySnakeCase = supportedCities[selectedCityIndex];
    const eventType = supportedEventTypes[typeIndex];
    const messageToSend = `${citySnakeCase}:${eventType}: Show me ${eventType} events in ${citiesDisplay[selectedCityIndex]}`;

    try {
      const request: ChatRequest = {
        message: messageToSend,
        conversation_history: conversationHistory,
        llm_provider: llmProvider,
        is_initial_response: conversationHistory.length <= 1,
        user_id: userId,
        conversation_id: conversationId
      };

      let recommendationCount = 0;
      let botMessage: ChatMessageWithRecommendations | null = null;

      await dataService.chatStream(
        request,
        () => {},
        (messageContent: string, metadata?: any) => {
          // We'll handle the message creation when we get recommendations
          console.log('📨 [handleEventTypeSelect] Received message:', messageContent);
          
          if (metadata?.trial_exceeded) {
            onTrialExceeded();
          }
          if (metadata?.conversation_id && metadata.conversation_id !== conversationId) {
            localStorage.setItem('current_conversation_id', metadata.conversation_id);
          }
        },
        (recommendation: any) => {
          const recTitle = recommendation?.data?.title || recommendation?.data?.data?.title || 'Unknown';
          console.log('📥 [handleEventTypeSelect] Received recommendation:', recTitle);
          
          recommendationCount++;
          
          // Create or update the bot message with the specific text and recommendations
          if (!botMessage) {
            botMessage = {
              role: 'assistant',
              content: `Found ${recommendationCount} events in ${citiesDisplay[selectedCityIndex]} that match your search! Check out the recommendations ↓`,
              timestamp: new Date().toISOString(),
              recommendations: [recommendation],
              showEvents: true
            };
            
            setMessages(prev => [...prev, botMessage!]);
            setMessagesWithRecommendations(prev => [...prev, botMessage!]);
            currentAssistantMessageIndexRef.current = -1; // Reset since we created a new message
            
            // Stop typing indicator as soon as the main message appears
            setIsTyping(false);
          } else {
            // Update the existing message with more recommendations and updated count
            botMessage = {
              ...botMessage,
              content: `Found ${recommendationCount} events in ${citiesDisplay[selectedCityIndex]} that match your search! Check out the recommendations ↓`,
              recommendations: [...(botMessage.recommendations || []), recommendation]
            };
            
            setMessages(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = botMessage!;
              return updated;
            });
            
            setMessagesWithRecommendations(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = botMessage!;
              return updated;
            });
          }
          
          onRecommendations([recommendation]);
        },
        (error: string) => {
          console.error('Streaming error:', error);
          const errorMessage: ChatMessage = {
            role: 'assistant',
            content: `Sorry, I encountered an error: ${error}`,
            timestamp: new Date().toISOString()
          };
          onNewMessage(errorMessage);
        },
        () => {
          setIsTyping(false);
          
          // If we got recommendations, notify parent about the final message
          if (botMessage) {
            onNewMessage(botMessage as ChatMessage);
          }
        }
      );
    } catch (error) {
      console.error('Error in handleEventTypeSelect:', error);
      setIsTyping(false);
    }
  };


  const handleLogin = () => {
    onLogin();
    setMenuOpen(false);
  };

  return (
    <div className="h-dvh bg-[#FCFBF9] flex flex-col max-w-md mx-auto">
      {/* Sticky Header Container */}
      <div className="sticky top-0 z-50 bg-[#FCFBF9] flex-shrink-0">
        {/* Header */}
        <div className="bg-[#FCFBF9] px-4 py-2.5 border-b border-slate-200/50 flex items-center gap-2">
          <button 
            onClick={() => setMenuOpen(true)}
            type="button"
            className="p-1.5 hover:bg-slate-200/50 rounded-lg transition-colors"
          >
            <Menu className="w-5 h-5" style={{ color: 'rgb(118, 193, 178)' }} />
          </button>
          <a 
            href="https://home.locomoco.top"
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 cursor-pointer hover:opacity-80 transition-opacity"
            style={{ 
              background: 'linear-gradient(135deg, #76C1B2 0%, #B46A55 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              fontFamily: 'Aladin, cursive',
              fontSize: '12px',
              textDecoration: 'none'
            }}
          >
            LocoMoco. Catch the Vibe. Locally
          </a>
          
          {/* Selection Icons in Header - Always visible */}
          <div className="flex items-center gap-1.5 relative">
            {/* Location Icon Button */}
            <div className="relative">
              <button
                onClick={() => {
                  setShowLocationDropdown(!showLocationDropdown);
                  setShowEventTypeDropdown(false);
                }}
                className="h-9 rounded-full shadow-sm flex items-center justify-center transition-all hover:shadow-md active:scale-95 px-2.5 gap-1.5"
                style={{ backgroundColor: '#E8E5DD' }}
              >
                <MapPin className="w-4 h-4" style={{ color: '#B46A55' }} />
                <span className="whitespace-nowrap" style={{ color: '#5E574E', fontFamily: 'Aladin, cursive', fontSize: '15px' }}>
                  {selectedCityIndex >= 0 ? citiesDisplay[selectedCityIndex] : 'city'}
                </span>
              </button>
              
              {/* Location Dropdown */}
              {showLocationDropdown && (
                <div className="absolute top-full right-0 mt-2 rounded-xl shadow-xl border max-h-[300px] overflow-y-auto w-48 z-50 animate-in fade-in slide-in-from-top-2 duration-200" style={{ backgroundColor: '#E8E5DD', borderColor: '#F5F5F5' }}>
                  {citiesDisplay.map((city, index) => (
                    <button
                      key={city}
                      onClick={() => {
                        handleCitySelect(index);
                        setShowLocationDropdown(false);
                      }}
                      className="w-full text-left px-4 py-3 hover:bg-[#FCFBF9] transition-colors first:rounded-t-xl last:rounded-b-xl"
                      style={{ 
                        color: '#5E574E',
                        fontFamily: 'Aladin, cursive',
                        fontSize: '14px',
                        backgroundColor: selectedCityIndex === index ? '#D4CFC2' : 'transparent'
                      }}
                    >
                      {city}
                    </button>
                  ))}
                </div>
              )}
            </div>
            
            {/* Event Type Icon Button */}
            <div className="relative">
              <button
                onClick={() => {
                  setShowEventTypeDropdown(!showEventTypeDropdown);
                  setShowLocationDropdown(false);
                }}
                className="h-9 rounded-full shadow-sm flex items-center justify-center transition-all hover:shadow-md active:scale-95 px-2.5 gap-1.5"
                style={{ backgroundColor: '#E8E5DD' }}
              >
                <Sparkles className="w-4 h-4" style={{ color: '#B46A55' }} />
                <span className="whitespace-nowrap lowercase" style={{ color: '#5E574E', fontFamily: 'Aladin, cursive', fontSize: '15px' }}>
                  {selectedEventTypeIndex >= 0 ? supportedEventTypes[selectedEventTypeIndex] : 'vibe'}
                </span>
              </button>
              
              {/* Event Type Dropdown */}
              {showEventTypeDropdown && (
                <div className="absolute top-full right-0 mt-2 rounded-xl shadow-xl border max-h-[300px] overflow-y-auto w-48 z-50 animate-in fade-in slide-in-from-top-2 duration-200" style={{ backgroundColor: '#E8E5DD', borderColor: '#F5F5F5' }}>
                  {supportedEventTypes.map((type, index) => (
                    <button
                      key={type}
                      onClick={() => {
                        handleEventTypeSelect(index);
                        setShowEventTypeDropdown(false);
                      }}
                      className="w-full text-left px-4 py-3 hover:bg-[#FCFBF9] transition-colors first:rounded-t-xl last:rounded-b-xl"
                      style={{ 
                        color: '#5E574E',
                        fontFamily: 'Aladin, cursive',
                        fontSize: '14px',
                        backgroundColor: selectedEventTypeIndex === index ? '#D4CFC2' : 'transparent'
                      }}
                    >
                      <span className="lowercase">{type}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Side Menu */}
      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent side="left" className="w-[85%] bg-[#FCFBF9] p-0" aria-describedby={undefined}>
          <SheetHeader className="sr-only">
            <SheetTitle>Menu</SheetTitle>
          </SheetHeader>
          <div className="flex flex-col h-full">
            {/* Menu Header */}
            <div className="p-6 border-b pt-16">
              {currentUser ? (
                <div>
                  <div className="w-16 h-16 rounded-full bg-slate-200 mb-3 overflow-hidden">
                    {currentUser.photoURL ? (
                      <img src={currentUser.photoURL} alt="Profile" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center" style={{ backgroundColor: '#E9E6DF' }}>
                        <span style={{ color: '#221A13', fontFamily: 'Aladin, cursive' }}>
                          {currentUser.displayName?.[0] || currentUser.email?.[0] || 'U'}
                        </span>
                      </div>
                    )}
                  </div>
                  <p style={{ color: '#221A13', fontFamily: 'Aladin, cursive' }}>Welcome back!</p>
                </div>
              ) : (
                <h2 style={{ color: '#221A13', fontFamily: 'Aladin, cursive' }}>Menu</h2>
              )}
            </div>

            {/* Menu Items */}
            <div className="flex-1 overflow-auto">
              <nav className="py-4">
                <button 
                  onClick={() => setMenuOpen(false)}
                  className="w-full flex items-center gap-4 px-6 py-4 hover:bg-slate-50 transition-colors text-left"
                >
                  <Home className="w-5 h-5" style={{ color: '#9A8B68' }} />
                  <span style={{ color: '#221A13', fontFamily: 'Aladin, cursive' }}>Home</span>
                </button>

                {authLoading ? (
                  <div className="px-6 py-4 text-sm" style={{ color: '#5E574E' }}>Loading...</div>
                ) : currentUser ? (
                  <>
                    <button 
                      onClick={async () => {
                        setMenuOpen(false);
                        await onLogout();
                      }}
                      className="w-full flex items-center gap-4 px-6 py-4 hover:bg-slate-50 transition-colors text-left mt-4 border-t"
                    >
                      <LogIn className="w-5 h-5" style={{ color: '#9A8B68' }} />
                      <span style={{ color: '#221A13' }}>Log out</span>
                    </button>
                  </>
                ) : (
                  <>
                    <button 
                      onClick={handleLogin}
                      className="w-full flex items-center gap-4 px-6 py-4 hover:bg-slate-50 transition-colors text-left"
                    >
                      <LogIn className="w-5 h-5" style={{ color: '#9A8B68' }} />
                      <span style={{ color: '#221A13', fontFamily: 'Aladin, cursive' }}>Log in</span>
                    </button>
                    <button 
                      onClick={() => {
                        setMenuOpen(false);
                        onRegister();
                      }}
                      className="w-full flex items-center gap-4 px-6 py-4 hover:bg-slate-50 transition-colors text-left"
                    >
                      <UserPlus className="w-5 h-5" style={{ color: '#9A8B68' }} />
                      <span style={{ color: '#221A13', fontFamily: 'Aladin, cursive' }}>Sign up</span>
                    </button>
                    {usageStats && !usageStats.is_registered && (
                      <div className="px-6 py-3 text-xs" style={{ color: '#5E574E' }}>
                        Trial: {usageStats.trial_remaining} interactions left
                      </div>
                    )}
                    <button 
                      onClick={() => {
                        // Redirect to Google Form for feedback
                        const googleFormUrl = 'https://docs.google.com/forms/d/e/1FAIpQLSeTvBTyvM00RJ2cx8DWm6Lrw1f4gfeab1q5zXJkwGYRUlWn8w/viewform';
                        window.open(googleFormUrl, '_blank');
                        setMenuOpen(false);
                      }}
                      className="w-full flex items-center gap-4 px-6 py-4 hover:bg-slate-50 transition-colors text-left"
                    >
                      <MessageSquare className="w-5 h-5" style={{ color: '#9A8B68' }} />
                      <span style={{ color: '#221A13', fontFamily: 'Aladin, cursive' }}>User Feedback</span>
                    </button>
                  </>
                )}
              </nav>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      {/* Trial Warning Banner */}
      {trialWarning && (
        <div className="fixed top-[57px] left-0 right-0 bg-amber-50 border-l-4 border-amber-500 p-4 z-40 max-w-md mx-auto">
          <p className="text-amber-700">{trialWarning}</p>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-h-0">
        {messages.length > 0 ? (
          <>
            {/* Chat Conversation - starts from top */}
            <div className="overflow-y-auto bg-[#FCFBF9] px-4 py-4 space-y-4 scrollbar-hide flex-1">
              {messages.map((message, index) => (
                message.role === 'user' ? (
                  /* User Message */
                  <div 
                    key={index} 
                    className="flex justify-end gap-2 items-start"
                    ref={index === lastUserMessageIndex ? lastUserMessageRef : null}
                  >
                    <div
                      className="rounded-xl rounded-tr-sm px-4 py-3 max-w-[80%] border shadow-sm"
                      style={{
                        backgroundColor: '#D4CFC2',
                        borderColor: '#D4CFC2',
                      }}
                    >
                      <p className="text-[15px]" style={{ color: '#221A13' }}>{message.content}</p>
                    </div>
                    {/* User Avatar */}
                    <div
                      className="w-11 h-11 rounded-full flex-shrink-0 flex items-center justify-center mt-1 overflow-hidden border-2"
                      style={{
                        backgroundColor: '#E9E6DF',
                        borderColor: '#D4CFC2',
                      }}
                    >
                      <img src={userProfilePic} alt="User" className="w-3/4 h-3/4 object-cover rounded-full" />
                    </div>
                  </div>
                ) : (
                  /* Bot Response with Cards */
                  <div key={index} className="flex gap-2 items-start">
                    {/* Bot Avatar */}
                    <div className="w-11 h-11 rounded-full flex-shrink-0 flex items-center justify-center mt-1 overflow-hidden p-1.5 border-2" style={{ backgroundColor: 'white', borderColor: 'rgba(118, 193, 178, 0.6)' }}>
                      <img src={agentAvatar} alt="Agent" className="w-4/5 h-4/5 object-cover" />
                    </div>
                    
                    {/* Bot Message */}
                    <div className="flex-1 space-y-3 min-w-0">
                      {message.content && (
                        <div 
                          className="bg-white rounded-xl rounded-tl-sm px-4 py-3 shadow-md border" 
                          style={{ borderColor: '#F5F5F5' }}
                        >
                          <p className="text-[15px]" style={{ color: '#221A13' }}>{message.content}</p>
                        </div>
                      )}

                      {/* Event Cards - Horizontal Scroll */}
                      {message.showEvents && message.recommendations && (
                        <div className="overflow-x-auto overflow-y-hidden -mx-1 scrollbar-hide">
                          <div className="flex gap-3 px-1 pb-2">
                            {message.recommendations.map((rec, recIndex) => (
                              <div key={recIndex} className="flex-shrink-0">
                                <RecommendationCard recommendation={rec} />
                              </div>
                            ))}
                            
                            {/* "More Specific" Card - Only show if we have follow-up suggestions */}
                            {selectedEventTypeIndex >= 0 && (() => {
                              const eventTypeColors = [
                                // '#F5B48A', // Peach
                                // '#8AD0C9', // Teal
                                // '#F8D27C', // Warm yellow
                                // '#8FB8FF', // Light blue
                                // '#D9E27A', // Soft chartreuse
                                // '#CDA0F6', // Lavender
                                // '#F4A3A0', // Soft rose
                                // '#FFAFA3'  // Coral
                                '#8AD0C9',
                                '#F8D27C',
                                '#8AD0C9',
                                '#F8D27C',
                                '#8AD0C9',
                                '#F8D27C',
                                '#8AD0C9',
                                '#F8D27C',
                                '#8AD0C9',
                                '#F8D27C',
                              ];
                              const eventColor = eventTypeColors[selectedEventTypeIndex];
                              // Create a lighter background color from the event color
                              const bgColor = eventColor + '15'; // Adding alpha for very light tint
                              
                              return (
                                <div
                                  className="flex-shrink-0 w-[240px] bg-white rounded-xl shadow-md border transition-all p-4 flex flex-col"
                                  style={{ borderColor: '#F5F5F5' }}
                                >
                                  <div className="flex-1 flex flex-col justify-center space-y-3">
                                    <div className="flex items-center justify-center w-12 h-12 rounded-full mx-auto" style={{ backgroundColor: bgColor }}>
                                      <Sparkles className="w-6 h-6" style={{ color: eventColor }} />
                                    </div>
                                    
                                    <h3 className="text-center" style={{ color: '#221A13', fontFamily: 'Abitare Sans, sans-serif', fontSize: '15px' }}>
                                      Something more specific?
                                    </h3>
                                    
                                    <div className="space-y-2 pt-2">
                                      {getFollowUpSuggestions(supportedEventTypes[selectedEventTypeIndex]).map((suggestion, index) => {
                                        return (
                                          <button
                                            key={index}
                                            onClick={() => handleSuggestionClick(suggestion.text)}
                                            className="w-full px-3 py-2.5 bg-white rounded-lg text-left hover:shadow-md transition-all shadow-sm border text-sm"
                                            style={{ 
                                              borderColor: '#F5F5F5',
                                              borderLeftWidth: '2px',
                                              borderLeftColor: eventColor,
                                              color: '#221A13'
                                            }}
                                          >
                                            {suggestion.text}
                                          </button>
                                        );
                                      })}
                                    </div>
                                  </div>
                                </div>
                              );
                            })()}
                          </div>
                        </div>
                      )}

                      {/* City Selection - Horizontal Scroll Chips */}
                      {message.showCitySelection && (
                        <div className="overflow-x-auto overflow-y-hidden -mx-1 scrollbar-hide">
                          <div className="flex gap-2 px-1 pb-2">
                            {citiesDisplay.map((city, index) => {
                              const colors = [
                                //'#E09C75', // Muted peach
                                //'#73B6AF', // Softer teal
                                //'#E4C063', // Muted yellow
                                //'#7EA4E6', // Softer blue
                                //'#C5D567', // Muted chartreuse
                                //'#B892E0', // Softer lavender
                                //'#E48E8A', // Muted rose
                                //'#F09588'  // Muted coral
                                '#E09C75',
                                '#A89F8F',
                                '#E09C75',
                                '#A89F8F',
                                '#E09C75',
                                '#A89F8F',
                                '#E09C75',
                                '#A89F8F',
                                '#E09C75',
                                '#A89F8F',
                              ];
                              const borderColor = colors[index % colors.length];
                              const backgroundColor = borderColor;
                              return (
                                <button
                                  key={city}
                                  onClick={() => handleCitySelect(index)}
                                  className="flex-shrink-0 px-4 py-2 rounded-xl shadow-sm border-2 transition-all hover:shadow-md active:scale-95 flex items-center gap-2"
                                  style={{ 
                                    borderColor,
                                    backgroundColor,
                                    color: '#FFFAF2' // near-white text for better contrast on colored chips
                                  }}
                                >
                                  <MapPin className="w-4 h-4" style={{ color: '#FFFAF2' }} />
                                  <span className="text-sm whitespace-nowrap">{city}</span>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* Event Type Selection - Horizontal Scroll Chips */}
                      {message.showEventTypeSelection && (
                        <div className="overflow-x-auto overflow-y-hidden -mx-1 scrollbar-hide">
                          <div className="flex gap-2 px-1 pb-2">
                            {supportedEventTypes.map((type, index) => {
                              const colors = [
                                // '#E09C75', // Muted peach
                                // '#73B6AF', // Softer teal
                                // '#E4C063', // Muted yellow
                                // '#7EA4E6', // Softer blue
                                // '#C5D567', // Muted chartreuse
                                // '#B892E0', // Softer lavender
                                // '#E48E8A', // Muted rose
                                // '#F09588'  // Muted coral
                                '#73B6AF', // Darker teal
                                //'#B8C98A', // Yellow-teal (closer to yellow)
                                '#A89F8F', // Darker yellow
                                '#73B6AF',
                                '#A89F8F',
                                '#73B6AF',
                                '#A89F8F',
                                '#73B6AF',
                                '#A89F8F',
                                '#73B6AF',
                                '#A89F8F',
                              ];
                              const borderColor = colors[index % colors.length];
                              const backgroundColor = borderColor;
                              return (
                                <button
                                  key={type}
                                  onClick={() => handleEventTypeSelect(index)}
                                  className="flex-shrink-0 px-4 py-2 rounded-xl shadow-sm border-2 transition-all hover:shadow-md active:scale-95 flex items-center gap-2"
                                  style={{ 
                                    borderColor,
                                    backgroundColor,
                                    color: '#FFFAF2' // near-white text for better contrast on colored chips
                                  }}
                                >
                                  {type === 'music' && <Music2 className="w-4 h-4" style={{ color: '#FFFAF2' }} />}
                                  {type === 'sports' && <Dumbbell className="w-4 h-4" style={{ color: '#FFFAF2' }} />}
                                  {type === 'nightlife' && <Wine className="w-4 h-4" style={{ color: '#FFFAF2' }} />}
                                  {type === 'business' && <Briefcase className="w-4 h-4" style={{ color: '#FFFAF2' }} />}
                                  {type === 'tech' && <Cpu className="w-4 h-4" style={{ color: '#FFFAF2' }} />}
                                  {type === 'dating' && <Heart className="w-4 h-4" style={{ color: '#FFFAF2' }} />}
                                  {type !== 'music' &&
                                   type !== 'sports' &&
                                   type !== 'nightlife' &&
                                   type !== 'business' &&
                                   type !== 'tech' &&
                                   type !== 'dating' && (
                                     <Sparkles className="w-4 h-4" style={{ color: '#FFFAF2' }} />
                                  )}
                                  <span className="text-sm whitespace-nowrap lowercase">{type}</span>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      )}

                    </div>
                  </div>
                )
              ))}

              {/* Typing Indicator */}
              {isTyping && (
                <div className="flex gap-2 items-start animate-in fade-in slide-in-from-bottom-2 duration-300">
                  <div className="w-11 h-11 rounded-full flex-shrink-0 flex items-center justify-center mt-1 overflow-hidden p-1.5 border-2 animate-pulse" style={{ backgroundColor: 'white', borderColor: 'rgb(118, 193, 178)' }}>
                    <img src={agentAvatar} alt="Agent" className="w-4/5 h-4/5 object-cover" />
                  </div>
                  <div className="bg-white rounded-lg rounded-tl-sm px-4 py-3 shadow-md border animate-pulse slide-in-from-bottom" style={{ borderColor: 'rgba(118, 193, 178, 0.2)' }}>
                    <div className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 bg-[#76C1B2] rounded-full animate-bounce" style={{ animationDelay: '0ms', animationDuration: '1.2s' }} />
                      <div className="w-2.5 h-2.5 bg-[#76C1B2] rounded-full animate-bounce" style={{ animationDelay: '200ms', animationDuration: '1.2s' }} />
                      <div className="w-2.5 h-2.5 bg-[#76C1B2] rounded-full animate-bounce" style={{ animationDelay: '400ms', animationDuration: '1.2s' }} />
                    </div>
                  </div>
                </div>
              )}
              
              {/* Centered Dancing Pet in Recommendations Area (only show after event type selection) */}
              {isTyping && hasCompletedInitialSelection && selectedEventTypeIndex >= 0 && (
                <div className="flex flex-col items-center justify-center py-16 px-4 animate-in fade-in duration-500">
                  <div className="mb-6">
                    <DancingPet gifSrc={catGif} size={100} />
                  </div>
                  <div className="flex items-center gap-1.5 mb-3">
                    <div className="w-2.5 h-2.5 bg-[#76C1B2] rounded-full animate-bounce" style={{ animationDelay: '0ms', animationDuration: '1.2s' }} />
                    <div className="w-2.5 h-2.5 bg-[#76C1B2] rounded-full animate-bounce" style={{ animationDelay: '200ms', animationDuration: '1.2s' }} />
                    <div className="w-2.5 h-2.5 bg-[#76C1B2] rounded-full animate-bounce" style={{ animationDelay: '400ms', animationDuration: '1.2s' }} />
                  </div>
                  <p className="text-sm" style={{ color: '#5E574E' }}>Finding the best events for you...</p>
                </div>
              )}
              
              {/* Skeleton Loaders for Recommendations (only show after event type selection, but hidden when dancing pet is shown) */}
              {isTyping && hasCompletedInitialSelection && selectedEventTypeIndex >= 0 && false && (
                <div className="flex gap-2 items-start mt-4">
                  <div className="w-11 h-11 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="overflow-x-auto overflow-y-hidden -mx-1 scrollbar-hide">
                      <div className="flex gap-3 px-1 pb-2">
                        {[1, 2, 3].map((i) => (
                          <div key={i} className="flex-shrink-0 w-[280px] animate-in fade-in slide-in-from-right duration-300" style={{ animationDelay: `${i * 100}ms` }}>
                            <div className="bg-white rounded-xl shadow-md border overflow-hidden animate-pulse" style={{ borderColor: 'rgba(118, 193, 178, 0.2)' }}>
                              {/* Image Skeleton */}
                              <div className="w-full h-40 bg-gradient-to-br from-slate-200 to-slate-300 animate-shimmer"></div>
                              {/* Content Skeleton */}
                              <div className="p-4 space-y-3">
                                <div className="h-5 bg-slate-200 rounded w-3/4 animate-pulse"></div>
                                <div className="h-4 bg-slate-200 rounded w-full animate-pulse"></div>
                                <div className="h-4 bg-slate-200 rounded w-2/3 animate-pulse"></div>
                                <div className="flex gap-2 mt-3">
                                  <div className="h-6 bg-slate-200 rounded-full w-20 animate-pulse"></div>
                                  <div className="h-6 bg-slate-200 rounded-full w-16 animate-pulse"></div>
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          /* Empty State - Centered Content */
          <div className="flex-1 flex flex-col items-center justify-center px-6 pb-32 bg-[#FCFBF9]">
            <h2 className="text-slate-900 mb-2 text-center" style={{ fontFamily: 'Aladin, cursive' }}>Discover Local Events</h2>
            <p className="text-slate-600 text-center text-sm mb-8">
              {hasCompletedInitialSelection ? 'Tap a suggestion below to get started' : 'Select your city and vibe to start'}
            </p>
            <div className="w-full space-y-3">
              {initialExamples.map((example, index) => (
                <button 
                  key={index}
                  disabled={!hasCompletedInitialSelection}
                  onClick={() => handleSuggestionClick(example.text)}
                  className="w-full px-4 py-4 bg-white rounded-xl text-left hover:shadow-md transition-all shadow-sm border border-slate-100 flex items-center gap-3 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:shadow-sm"
                  style={{ color: '#221A13' }}
                >
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 bg-[#FCFBF9]">
                    <img src={example.icon} alt="" className="w-6 h-6" />
                  </div>
                  <span className="text-sm">{example.text}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input Area - Always at Bottom */}
        <div className="px-4 py-4 flex-shrink-0 relative border-t" style={{ backgroundColor: '#FCFBF9', borderColor: '#E5E3DC' }}>
          {/* Input Form */}
          <form onSubmit={handleSubmit} className="flex gap-3 items-center relative">
            <Input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e as any);
                }
              }}
              placeholder={messages.length > 1 ? "What else are you looking for?" : "What vibe are you looking for?"}
              className="flex-1 rounded-xl border h-14 text-base px-6"
              style={{ 
                backgroundColor: 'white',
                borderColor: '#E5E3DC',
                color: '#221A13'
              }}
            />
            <button
              type="submit"
              className="rounded-full hover:bg-slate-50 h-14 w-14 flex items-center justify-center transition-all shadow-sm border active:scale-90 active:shadow-lg"
              style={{ 
                backgroundColor: 'white',
                borderColor: '#E5E3DC'
              }}
            >
              <Send className="w-7 h-7" style={{ color: '#B46A55' }} />
            </button>
          </form>
        </div>
      </div>

    </div>
  );
}

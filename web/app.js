const { createApp, ref, computed } = Vue;

createApp({
  setup() {
    const documents = ref([
      "Michael Jeffrey Jordan is a former professional basketball player who born in 1963.",
      "Micheal Iwris Jordan was born on February 17, 2000, in Brooklyn, New York City.",
      "Michael Jordan is a farmer who born in 1888.",
    ]);
    const query = ref("What year was Michael Jordan born?");
    const rounds = ref(2);
    const topK = ref(6);
    const isRunning = ref(false);
    const steps = ref([]);
    const visibleSteps = ref([]);
    const currentSpeech = ref("");
    const finalAnswer = ref("");
    const errorMessage = ref("");
    const stats = ref(null);
    const showInputs = ref(true);
    const showLog = ref(false);
    const showStage = ref(false);
    let playbackTimer = null;
    let playbackQueue = [];
    let streamDone = false;
    let socket = null;
    let receivedAny = false;

    const sanitizedDocs = (docs) =>
      docs.map((doc) => doc.trim()).filter(Boolean).slice(0, 4);

    const addDoc = () => {
      if (documents.value.length < 4) {
        documents.value.push("");
      }
    };

    const removeDoc = (index) => {
      documents.value.splice(index, 1);
    };

    const stageLabel = (step) => {
      switch (step.stage) {
        case "setup":
          return "Setup";
        case "indexing":
          return "Indexing";
        case "retrieval":
          return "Retrieval";
        case "evidence":
          return "Evidence";
        case "ambiguity":
          return "Ambiguity";
        case "debate":
          return "Debate";
        case "synthesis":
          return "Synthesis";
        default:
          return "Step";
      }
    };

    const agentCount = computed(() => {
      const docIds = new Set();
      for (const step of steps.value) {
        if (step.doc_id) {
          docIds.add(step.doc_id);
        }
      }
      const count = docIds.size || 1;
      return Math.min(3, count);
    });

    const activeAgentIndex = computed(() => {
      if (!visibleSteps.value.length) {
        return 0;
      }
      const lastStep = visibleSteps.value[visibleSteps.value.length - 1];
      if (!lastStep || !lastStep.doc_id) {
        return 0;
      }
      const index = ((lastStep.doc_id - 1) % agentCount.value) + 1;
      return index;
    });

    const activeAgentLabel = computed(() => {
      if (!visibleSteps.value.length) {
        return "";
      }
      const lastStep = visibleSteps.value[visibleSteps.value.length - 1];
      if (lastStep?.doc_id) {
        const index = ((lastStep.doc_id - 1) % agentCount.value) + 1;
        return `Agent ${index}`;
      }
      return lastStep?.speaker || "";
    });

    const speakerX = computed(() => "28%");

    const currentStageText = computed(() => {
      if (!visibleSteps.value.length) {
        return "Waiting";
      }
      const lastStep = visibleSteps.value[visibleSteps.value.length - 1];
      if (!lastStep) {
        return "Waiting";
      }
      switch (lastStep.stage) {
        case "setup":
          return "Setup";
        case "indexing":
          return "Embedding";
        case "retrieval":
          return "Retrieval";
        case "evidence":
          return "Evidence Gathering";
        case "ambiguity":
          return lastStep.round
            ? `Ambiguity Check (Round ${lastStep.round})`
            : "Ambiguity Check";
        case "debate":
          return lastStep.round
            ? `Debate Round ${lastStep.round}`
            : "Debate";
        case "synthesis":
          return "Synthesize Answer";
        default:
          return "Processing";
      }
    });

    const stageProgress = computed(() => {
      const stages = [
        { key: "embedding", label: "Embedding" },
        { key: "retrieval", label: "Retrieval" },
        { key: "evidence", label: "Evidence Gathering" },
        { key: "ambiguity-0", label: "Ambiguity Check" },
      ];

      const roundCount = Math.min(4, Math.max(1, Number(rounds.value) || 1));
      for (let i = 1; i <= roundCount; i += 1) {
        stages.push({ key: `debate-${i}`, label: `Debate Round ${i}` });
        stages.push({
          key: `ambiguity-${i}`,
          label: `Ambiguity Check (Round ${i})`,
        });
      }

      stages.push({ key: "synthesis", label: "Synthesize Answer" });

      const lastStep = visibleSteps.value[visibleSteps.value.length - 1];
      let currentKey = "";
      if (lastStep) {
        if (lastStep.stage === "indexing") currentKey = "embedding";
        else if (lastStep.stage === "retrieval") currentKey = "retrieval";
        else if (lastStep.stage === "evidence") currentKey = "evidence";
        else if (lastStep.stage === "debate")
          currentKey = `debate-${lastStep.round || 1}`;
        else if (lastStep.stage === "ambiguity")
          currentKey = `ambiguity-${lastStep.round || 0}`;
        else if (lastStep.stage === "synthesis") currentKey = "synthesis";
      }

      const currentIndex = stages.findIndex((stage) => stage.key === currentKey);
      return stages.map((stage, index) => {
        let status = "pending";
        if (currentIndex === -1) {
          status = "pending";
        } else if (index < currentIndex) {
          status = "done";
        } else if (index === currentIndex) {
          status = "active";
        }
        return { ...stage, status };
      });
    });

    const stopPlayback = () => {
      if (playbackTimer) {
        clearInterval(playbackTimer);
        playbackTimer = null;
      }
    };

    const startStreamingPlayback = () => {
      if (playbackTimer) {
        return;
      }
      playbackTimer = setInterval(() => {
        if (!playbackQueue.length) {
          if (streamDone) {
            stopPlayback();
            currentSpeech.value = "Debate complete.";
          }
          return;
        }
        const step = playbackQueue.shift();
        visibleSteps.value.push(step);
        currentSpeech.value = step.message;
      }, 700);
    };

    const playSteps = (allSteps) => {
      stopPlayback();
      visibleSteps.value = [];
      currentSpeech.value = "";
      finalAnswer.value = "";

      let index = 0;
      playbackTimer = setInterval(() => {
        if (index >= allSteps.length) {
          stopPlayback();
          currentSpeech.value = "Debate complete.";
          const last = allSteps.findLast
            ? allSteps.findLast((step) => step.stage === "synthesis")
            : [...allSteps].reverse().find((step) => step.stage === "synthesis");
          if (last) {
            finalAnswer.value = last.message;
          }
          return;
        }

        const step = allSteps[index];
        visibleSteps.value.push(step);
        currentSpeech.value = step.message;
        index += 1;
      }, 900);
    };

    const runDebate = async () => {
      errorMessage.value = "";
      const docs = sanitizedDocs(documents.value);
      const safeRounds = Math.min(4, Math.max(1, Number(rounds.value) || 1));
      if (!docs.length || !query.value.trim()) {
        errorMessage.value = "Please provide at least one document and a question.";
        return;
      }
      if (!window.location.host) {
        errorMessage.value =
          "Please open this page from the FastAPI server (e.g. http://127.0.0.1:8000/).";
        return;
      }

      isRunning.value = true;
      showInputs.value = false;
      showLog.value = false;
      showStage.value = true;
      stopPlayback();
      playbackQueue = [];
      streamDone = false;
      receivedAny = false;
      steps.value = [];
      visibleSteps.value = [];
      currentSpeech.value = "";
      finalAnswer.value = "";
      stats.value = null;

      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const wsUrl = `${protocol}://${window.location.host}/ws/debate`;

      if (socket) {
        socket.close();
      }

      socket = new WebSocket(wsUrl);
      socket.onopen = () => {
        socket.send(
          JSON.stringify({
            documents: docs,
            query: query.value.trim(),
            rounds: safeRounds,
            top_k: topK.value,
          })
        );
      };

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        receivedAny = true;
        if (data.event === "ready") {
          currentSpeech.value = "Debate starting...";
          return;
        }
        if (data.event === "step") {
          steps.value.push(data.data);
          playbackQueue.push(data.data);
          startStreamingPlayback();
          return;
        }
        if (data.event === "done") {
          stats.value = data.stats || null;
          finalAnswer.value = data.final_answer || "";
          streamDone = true;
          isRunning.value = false;
          return;
        }
        if (data.event === "error") {
          if (typeof data.detail === "string") {
            errorMessage.value = data.detail;
          } else {
            errorMessage.value = JSON.stringify(data.detail);
          }
          streamDone = true;
          isRunning.value = false;
        }
      };

      socket.onerror = () => {
        errorMessage.value = "WebSocket error. Please try again.";
        streamDone = true;
        isRunning.value = false;
      };

      socket.onclose = () => {
        if (!streamDone && !receivedAny) {
          errorMessage.value =
            "WebSocket closed before any data arrived. Check server logs and OPENAI_API_KEY.";
          isRunning.value = false;
        }
        socket = null;
      };
    };

    const replay = () => {
      if (steps.value.length) {
        playSteps(steps.value);
      }
    };

    const restart = () => {
      stopPlayback();
      if (socket) {
        socket.close();
        socket = null;
      }
      playbackQueue = [];
      streamDone = false;
      receivedAny = false;
      steps.value = [];
      visibleSteps.value = [];
      currentSpeech.value = "";
      finalAnswer.value = "";
      errorMessage.value = "";
      stats.value = null;
      showInputs.value = true;
      showLog.value = false;
      showStage.value = false;
    };

    const toggleLog = () => {
      showLog.value = !showLog.value;
    };

    return {
      documents,
      query,
      rounds,
      topK,
      isRunning,
      steps,
      visibleSteps,
      currentSpeech,
      finalAnswer,
      errorMessage,
      stats,
      showInputs,
      showLog,
      showStage,
      agentCount,
      activeAgentIndex,
      activeAgentLabel,
      speakerX,
      currentStageText,
      stageProgress,
      stageLabel,
      runDebate,
      addDoc,
      removeDoc,
      replay,
      restart,
      toggleLog,
    };
  },
}).mount("#app");

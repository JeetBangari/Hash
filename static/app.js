const API_URL = "";
let chatHistory = [];
let currentMode = "demo";

function toggleAuthMode(mode) {
    if (mode === 'signup') {
        document.getElementById('login-section').classList.add('hidden');
        document.getElementById('signup-section').classList.remove('hidden');
    } else {
        document.getElementById('signup-section').classList.add('hidden');
        document.getElementById('login-section').classList.remove('hidden');
    }
}

async function signup() {
    const name = document.getElementById("signup-name").value;
    const email = document.getElementById("signup-email").value;
    const password = document.getElementById("signup-password").value;

    if (!name || !email || !password) return alert("Please fill in all fields.");

    try {
        const res = await fetch(`${API_URL}/signup`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, email, password })
        });

        const data = await res.json();
        if (res.ok) {
            alert("Account created successfully! Please log in.");
            toggleAuthMode('login');
            document.getElementById("email").value = email; 
        } else {
            alert("Sign Up Failed: " + (data.detail || "Unknown error"));
        }
    } catch (e) {
        alert("Server error. Could not connect to backend.");
    }
}

async function login() {
    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;
    try {
        const res = await fetch(`${API_URL}/login`, { 
            method: "POST", 
            headers: { 
                "Content-Type": "application/json",
                "ngrok-skip-browser-warning": "true"
            }, 
            body: JSON.stringify({ email, password }) 
        });
        if (res.ok) {
            document.getElementById("login-section").classList.add("hidden");
            document.getElementById("otp-section").classList.remove("hidden");
            sessionStorage.setItem("login_email", email); 
        } else { 
            const errorData = await res.json();
            alert("Login Failed: " + (errorData.detail || "Unknown error")); 
        }
    } catch (e) { 
        alert("Server error. Check if API_URL is correct and Ngrok is running."); 
        console.error("Login Error:", e);
    }
}

async function verifyOTP() {
    const email = sessionStorage.getItem("login_email");
    const otp = document.getElementById("otp").value;
    const res = await fetch(`${API_URL}/verify-otp`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, otp }) });
    if (res.ok) {
        const data = await res.json();
        localStorage.setItem("user_data", JSON.stringify(data.user_data));
        initDashboard();
    } else { alert("Invalid OTP"); }
}

function logout() {
    localStorage.removeItem("user_data");
    sessionStorage.removeItem("login_email");
    location.reload();
}

function initDashboard() {
    const user = JSON.parse(localStorage.getItem("user_data"));
    if (!user) return;

    document.getElementById("auth-layer").classList.add("hidden");
    document.getElementById("sidebar").classList.remove("hidden");
    document.getElementById("main-content").classList.remove("hidden");
    
    document.getElementById("user-name").innerText = user.name;
    
    if (user.role === "admin") {
        document.getElementById("btn-admin").classList.remove("hidden");
        loadAdminRequests();
    }

    toggleMode(); 
    renderWatchlist();
    searchNews(); 
}

async function refreshUserData() {
    const user = JSON.parse(localStorage.getItem("user_data"));
    const res = await fetch(`${API_URL}/user-data`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: user.email }) });
    if (res.ok) {
        const data = await res.json();
        localStorage.setItem("user_data", JSON.stringify(data.user_data));
        toggleMode(); 
        renderWatchlist();
    }
}

function switchTab(tabId, btn) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
    btn.classList.add('active');
}

function toggleMode() {
    currentMode = document.getElementById("trading-mode").value;
    const user = JSON.parse(localStorage.getItem("user_data"));
    if (!user) return;
    
    if (currentMode === "demo") {
        document.getElementById("user-balance-label").innerText = "Virtual Cash:";
        document.getElementById("user-balance").innerText = `₹${user.virtual_balance.toLocaleString()}`;
        document.getElementById("desk-title").innerText = "🏦 Paper Trading Execution Desk";
        document.getElementById("trade-btn").innerText = "Execute Demo Order";
        document.getElementById("trade-btn").style.backgroundColor = "#ff4b4b";
        
        document.getElementById("btn-request-demo").style.display = "block";
        document.getElementById("liveFundButtons").style.display = "none";
    } else {
        document.getElementById("user-balance-label").innerText = "Live Margin:";
        document.getElementById("user-balance").innerText = `₹${user.live_balance.toLocaleString()}`;
        document.getElementById("desk-title").innerText = "🔴 LIVE Execution Desk";
        document.getElementById("trade-btn").innerText = "EXECUTE LIVE ORDER";
        document.getElementById("trade-btn").style.backgroundColor = "#d32f2f";
        
        document.getElementById("btn-request-demo").style.display = "none";
        document.getElementById("liveFundButtons").style.display = "flex";
    }
    
    renderPortfolio(); 
    renderOrderHistory();
}

async function analyzeStocks() {
    const tickerInput = document.getElementById("tickers").value;
    if (!tickerInput) return alert("Enter a ticker.");
    
    const tickersArray = tickerInput.split(",").map(t => t.trim());
    const grid = document.getElementById("results-grid");
    
    if(document.getElementById("loading-spinner")) {
        document.getElementById("loading-spinner").classList.remove("hidden");
    }
    grid.innerHTML = "<div style='color: #333; font-weight: bold;'>Loading AI Analysis... Please wait.</div>"; 

    try {
        const res = await fetch(`${API_URL}/analyze`, { 
            method: "POST", 
            headers: { "Content-Type": "application/json" }, 
            body: JSON.stringify({ tickers: tickersArray }) 
        });
        const result = await res.json();
        
        if(document.getElementById("loading-spinner")) {
            document.getElementById("loading-spinner").classList.add("hidden");
        }
        grid.innerHTML = ""; 

        for (const [ticker, data] of Object.entries(result.data)) {
            const ai = data.ai_analysis || {};
            const safeChartId = `chart-${ticker.replace('.', '-')}`;
            
            const call = ai.decision_call || "HOLD";
            const target = ai.target_price || "TBD";
            const sl = ai.stop_loss || "TBD";
            const period = ai.time_period || "1-3 Months";
            const reasoning = ai.fundamental_reasoning || "AI analysis currently unavailable.";

            if(document.getElementById("trade-ticker")) {
                document.getElementById("trade-ticker").value = ticker;
                
                if(target !== "TBD" && target !== "-") document.getElementById("trade-tp").value = parseFloat(target);
                if(sl !== "TBD" && sl !== "-") document.getElementById("trade-sl").value = parseFloat(sl);
            }

            let callColor = "#ffffff";
            if (call.toUpperCase().includes("BUY")) callColor = "#26a69a"; 
            if (call.toUpperCase().includes("SELL")) callColor = "#ef5350"; 
            if (call.toUpperCase().includes("HOLD")) callColor = "#ffb74d"; 

            const card = document.createElement('div');
            card.className = "ai-stock-card"; 
            
            card.innerHTML = `
                <h2 class="ai-stock-header">
                    ${ticker} 
                    <button onclick="toggleWatchlist('${ticker}')" style="background:none; color:gold; font-size:24px; padding:0; cursor:pointer; border:none;" title="Add to Watchlist">⭐</button>
                </h2>
                
                <div class="ai-metrics-container">
                    <div class="ai-metric-box" style="border-top: 3px solid #3498db;">
                        <span class="ai-metric-label">Live Price</span><br>
                        <strong class="ai-metric-value">₹${data.live_price || "N/A"}</strong>
                    </div>

                    <div class="ai-metric-box" style="border-top: 3px solid ${callColor};">
                        <span class="ai-metric-label">AI Call</span><br>
                        <strong class="ai-metric-value" style="color: ${callColor};">${call}</strong>
                    </div>

                    <div class="ai-metric-box" style="border-top: 3px solid #26a69a;">
                        <span class="ai-metric-label">Target (₹)</span><br>
                        <strong class="ai-metric-value" style="color: #26a69a;">${target}</strong>
                    </div>

                    <div class="ai-metric-box" style="border-top: 3px solid #ef5350;">
                        <span class="ai-metric-label">Stop Loss (₹)</span><br>
                        <strong class="ai-metric-value" style="color: #ef5350;">${sl}</strong>
                    </div>

                    <div class="ai-metric-box" style="border-top: 3px solid #9b59b6;">
                        <span class="ai-metric-label">Timeframe</span><br>
                        <strong class="ai-metric-value" style="font-size: 20px;">${period}</strong>
                    </div>
                </div>

                <div id="${safeChartId}" class="ai-chart-container"></div>
                
                <div class="ai-reasoning-box" style="border-left: 5px solid ${callColor};">
                    <h3 class="ai-reasoning-title" style="color: ${callColor};">
                        🤖 AI Strategy Rationale
                    </h3>
                    <p class="ai-reasoning-text">${reasoning}</p>
                </div>
            `;
            grid.appendChild(card);

            if (data.chart_data && data.chart_data.length > 0) {
                const x = data.chart_data.map(d => d.time);
                const trace = { 
                    x: x, 
                    open: data.chart_data.map(d=>d.open), 
                    high: data.chart_data.map(d=>d.high), 
                    low: data.chart_data.map(d=>d.low), 
                    close: data.chart_data.map(d=>d.close), 
                    type: 'candlestick',
                    increasing: {line: {color: '#26a69a'}},
                    decreasing: {line: {color: '#ef5350'}}
                };
                const layout = {
                    margin: {t:20, b:40, l:50, r:20}, 
                    xaxis:{rangeslider:{visible:false}, gridcolor: '#444', tickfont: {color: '#aaa'}},
                    yaxis:{gridcolor: '#444', tickfont: {color: '#aaa'}},
                    paper_bgcolor: 'rgba(0,0,0,0)',
                    plot_bgcolor: 'rgba(0,0,0,0)'
                };
                Plotly.newPlot(safeChartId, [trace], layout, {responsive: true});
            }
        }
    } catch (e) { 
        console.error("Analysis failed:", e);
        grid.innerHTML = `<div style="color:#ef5350; font-weight: bold;">Analysis failed to load. Check backend logs.</div>`;
    }
}

async function searchNews() {
    const query = document.getElementById("news-search") ? document.getElementById("news-search").value : "";
    const container = document.getElementById("news-container");
    container.innerHTML = "Loading...";
    
    try {
        const res = await fetch(`${API_URL}/market-updates?query=${encodeURIComponent(query)}`, {
            method: "GET",
            headers: {
                "ngrok-skip-browser-warning": "true" 
            }
        });
        
        if (!res.ok) {
            throw new Error(`Server Error: ${res.status} ${res.statusText}`);
        }

        const rawText = await res.text();
        
        try {
            const data = JSON.parse(rawText);
            
            if (!data.articles || data.articles.length === 0) {
                container.innerHTML = "No recent market updates found for this search.";
                return;
            }
            
            container.innerHTML = data.articles.map(a => `<div style="margin-bottom:10px;">• <a href="${a.url}" target="_blank" style="color:white; text-decoration:none;"><b>${a.title}</b></a></div>`).join("");
            
        } catch (jsonError) {
            if (rawText.includes("ngrok")) {
                throw new Error("Ngrok blocked the request despite bypass.");
            } else {
                throw new Error("Received invalid data from the server. Not JSON.");
            }
        }

    } catch (e) {
        console.error("News Fetch Diagnostic Error:", e);
        container.innerHTML = `<span style="color:#ffbaba;"><b>Diagnostic Error:</b> ${e.message}</span>`;
    }
}

async function executeTrade() {
    if (currentMode === "live") {
        alert("Live trading API is currently disconnected. Switch to Demo Mode to test strategies.");
        return;
    }

    const user = JSON.parse(localStorage.getItem("user_data"));
    const req = {
        email: user.email,
        ticker: document.getElementById("trade-ticker").value.toUpperCase(),
        action: document.getElementById("trade-action").value,
        quantity: parseInt(document.getElementById("trade-qty").value),
        stop_loss: parseFloat(document.getElementById("trade-sl").value),
        target_price: parseFloat(document.getElementById("trade-tp").value)
    };
    
    try {
        const res = await fetch(`${API_URL}/trade`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
        const data = await res.json();
        
        if (res.ok) {
            alert(data.message);
            refreshUserData();
        } else {
            alert("Trade Declined: " + (data.detail || data.message || "Unknown error occurred."));
        }
    } catch (e) {
        alert("Network Error: Could not reach the trading server.");
    }
}

async function renderPortfolio() {
    const user = JSON.parse(localStorage.getItem("user_data"));
    const body = document.getElementById("portfolio-body");
    body.innerHTML = "<tr><td colspan='10'>Loading live prices...</td></tr>";

    document.getElementById("total-invested").innerText = "₹0.00";
    document.getElementById("total-current").innerText = "₹0.00";
    document.getElementById("total-pnl").innerText = "₹0.00";
    document.getElementById("total-pnl").style.color = "#31333F";
    
    try {
        const res = await fetch(`${API_URL}/portfolio-data`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: user.email, mode: currentMode })
        });
        const data = await res.json();
        body.innerHTML = "";
        
        if (data.portfolio.length === 0) {
            body.innerHTML = "<tr><td colspan='10'>No active holdings.</td></tr>";
            return;
        }

        let grandTotalInvested = 0;
        let grandTotalCurrent = 0;
        
        data.portfolio.forEach(p => {
            grandTotalInvested += p.invested;
            grandTotalCurrent += p.current_value;

            const color = p.pnl >= 0 ? "#26a69a" : "#ef5350";
            const sign = p.pnl >= 0 ? "+" : "";
            
            const displayTP = p.target_price > 0 ? `₹${p.target_price.toFixed(2)}` : "-";
            const displaySL = p.stop_loss > 0 ? `₹${p.stop_loss.toFixed(2)}` : "-";

            body.innerHTML += `<tr>
                <td><b>${p.ticker}</b></td>
                <td>${p.shares}</td>
                <td>₹${p.avg_price.toFixed(2)}</td>
                <td>₹${p.live_price.toFixed(2)}</td>
                <td style="color:#26a69a; font-weight:bold;">${displayTP}</td>
                <td style="color:#ef5350; font-weight:bold;">${displaySL}</td>
                <td>₹${p.invested.toFixed(2)}</td>
                <td>₹${p.current_value.toFixed(2)}</td>
                <td style="color:${color}; font-weight:bold;">${sign}₹${p.pnl.toFixed(2)} (${sign}${p.pnl_pct.toFixed(2)}%)</td>
                <td>
                    <div style="display: flex; gap: 5px;">
                        <button onclick="document.getElementById('trade-ticker').value='${p.ticker}'; document.getElementById('trade-action').value='BUY'; switchTab('tab-terminal', document.querySelector('.nav-btn'));" style="padding:5px 10px; font-size:12px; background:#26a69a; color:white; border:none; border-radius:3px; cursor:pointer;">Buy</button>
                        <button onclick="document.getElementById('trade-ticker').value='${p.ticker}'; document.getElementById('trade-action').value='SELL'; switchTab('tab-terminal', document.querySelector('.nav-btn'));" style="padding:5px 10px; font-size:12px; background:#ef5350; color:white; border:none; border-radius:3px; cursor:pointer;">Sell</button>
                    </div>
                </td>
            </tr>`;
        });

        const grandTotalPnl = grandTotalCurrent - grandTotalInvested;
        const grandTotalPnlPct = grandTotalInvested > 0 ? (grandTotalPnl / grandTotalInvested) * 100 : 0;
        const pnlColor = grandTotalPnl >= 0 ? "#26a69a" : "#ef5350";
        const pnlSign = grandTotalPnl >= 0 ? "+" : "";

        document.getElementById("total-invested").innerText = `₹${grandTotalInvested.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        document.getElementById("total-current").innerText = `₹${grandTotalCurrent.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        
        const pnlElement = document.getElementById("total-pnl");
        pnlElement.innerText = `${pnlSign}₹${grandTotalPnl.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})} (${pnlSign}${grandTotalPnlPct.toFixed(2)}%)`;
        pnlElement.style.color = pnlColor;

    } catch (e) {
        body.innerHTML = "<tr><td colspan='10'>Failed to load portfolio data.</td></tr>";
    }
}

function renderOrderHistory() {
    const user = JSON.parse(localStorage.getItem("user_data"));
    const histBody = document.getElementById("history-body");
    const historyData = currentMode === "demo" ? (user.demo_order_history || []) : (user.live_order_history || []);
    
    if(historyData.length === 0) {
        histBody.innerHTML = "<tr><td colspan='5'>No orders found.</td></tr>";
        return;
    }
    
    histBody.innerHTML = [...historyData].reverse().map(o => `<tr><td>${o.Date}</td><td><b>${o.Ticker}</b></td><td><span style="color:${o.Action==='BUY'?'#26a69a':'#ef5350'}; font-weight:bold;">${o.Action}</span></td><td>${o.Quantity}</td><td>₹${o['Exec. Price (₹)']}</td></tr>`).join("");
}

async function toggleWatchlist(ticker) {
    const user = JSON.parse(localStorage.getItem("user_data"));
    await fetch(`${API_URL}/watchlist`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: user.email, ticker }) });
    refreshUserData(); 
}

async function renderWatchlist() {
    const user = JSON.parse(localStorage.getItem("user_data"));
    const body = document.getElementById("watchlist-body");
    body.innerHTML = "<tr><td colspan='4'>Loading live market data...</td></tr>";
    
    try {
        const res = await fetch(`${API_URL}/watchlist-data`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: user.email })
        });
        const data = await res.json();
        body.innerHTML = "";
        
        if (data.watchlist.length === 0) {
            body.innerHTML = "<tr><td colspan='4'>Watchlist is empty. Search a ticker in the terminal to add one.</td></tr>";
            return;
        }
        
        data.watchlist.forEach(item => {
            const color = item.change >= 0 ? "#26a69a" : "#ef5350";
            const sign = item.change >= 0 ? "+" : "";
            const displayPrice = item.live_price > 0 ? `₹${item.live_price.toFixed(2)}` : "Unavailable";
            const displayChange = item.live_price > 0 ? `<span style="color:${color}; font-weight:bold;">${sign}₹${item.change.toFixed(2)} (${sign}${item.pct_change.toFixed(2)}%)</span>` : "-";
            
            body.innerHTML += `<tr>
                <td><b>${item.ticker}</b></td>
                <td>${displayPrice}</td>
                <td>${displayChange}</td>
                <td>
                    <button onclick="document.getElementById('tickers').value='${item.ticker}'; analyzeStocks(); switchTab('tab-terminal', document.querySelector('.nav-btn'));" style="padding:5px 10px; background:#26a69a; color:white; border:none; border-radius:3px; cursor:pointer; margin-right: 5px;">Analyze</button>
                    <button onclick="toggleWatchlist('${item.ticker}')" style="padding:5px 10px; background:#ef5350; color:white; border:none; border-radius:3px; cursor:pointer;">Remove</button>
                </td>
            </tr>`;
        });
    } catch (e) {
        body.innerHTML = "<tr><td colspan='4'>Failed to load watchlist data.</td></tr>";
    }
}

async function requestFunds() {
    const user = JSON.parse(localStorage.getItem("user_data"));
    const amt = prompt("Amount to request (₹):", "10000");
    if (amt) {
        const res = await fetch(`${API_URL}/fund-request`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: user.email, amount: parseFloat(amt) }) });
        alert((await res.json()).message);
    }
}

function handleAddFunds() {
    let amount = prompt("Enter amount to add to your Live Margin (₹):");
    if (amount && !isNaN(amount) && amount > 0) {
        alert("Redirecting to secure payment gateway to add ₹" + amount + "...");
    }
}

function handleWithdrawFunds() {
    let amount = prompt("Enter amount to withdraw from your Live Margin (₹):");
    if (amount && !isNaN(amount) && amount > 0) {
        alert("Withdrawal request for ₹" + amount + " submitted. It will reflect in your bank account in 2-3 working days.");
    }
}

async function loadAdminRequests() {
    const user = JSON.parse(localStorage.getItem("user_data"));
    const res = await fetch(`${API_URL}/admin/requests?email=${user.email}`);
    if (res.ok) {
        const data = await res.json();
        document.getElementById("admin-body").innerHTML = data.requests.map(r => `<tr><td>${r.email}</td><td>₹${r.amount}</td>
        <td><button onclick="processRequest('${r.email}', '${r.timestamp}', 'approved')" style="background:green;">Approve</button>
        <button onclick="processRequest('${r.email}', '${r.timestamp}', 'rejected')">Reject</button></td></tr>`).join("");
    }
}

async function processRequest(targetEmail, timestamp, action) {
    const user = JSON.parse(localStorage.getItem("user_data"));
    await fetch(`${API_URL}/admin/process`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: user.email, target_email: targetEmail, timestamp, action }) });
    loadAdminRequests();
}

async function sendChatMessage() {
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text) return;
    
    const box = document.getElementById("chat-box");
    box.innerHTML += `<div class="msg-user">${text}</div>`;
    input.value = "";
    
    const user = JSON.parse(localStorage.getItem("user_data"));
    const req = { email: user.email, prompt: text, messages: chatHistory };
    
    try {
        const res = await fetch(`${API_URL}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
        const data = await res.json();
        chatHistory.push({role: "user", content: text}, {role: "assistant", content: data.response});
        box.innerHTML += `<div class="msg-ai">🤖 ${data.response}</div>`;
        box.scrollTop = box.scrollHeight;
    } catch (e) { box.innerHTML += `<div class="msg-ai" style="color:red;">Error connecting to AI.</div>`; }
}

if (localStorage.getItem("user_data")) initDashboard();

let filterTimer = null;

function nextFrame() {
    return new Promise((resolve) => requestAnimationFrame(resolve));
}

function filterChannels() {
    if (filterTimer) clearTimeout(filterTimer);
    filterTimer = setTimeout(() => {
        const query = document.getElementById("search-box").value.toLowerCase().trim();
        document.querySelectorAll(".group-container").forEach((group) => {
            let hasVisible = false;
            group.querySelectorAll(".channel-item").forEach((item) => {
                const chName = item.dataset.name || item.querySelector(".channel-name").innerText.toLowerCase();
                const visible = !query || chName.includes(query);
                item.style.display = visible ? "flex" : "none";
                if (visible) hasVisible = true;
            });
            group.style.display = hasVisible ? "block" : "none";
        });
    }, 120);
}

async function renderChannelList() {
    const listElement = document.getElementById("channel-list");
    const dataSource = typeof channelsData !== "undefined" ? channelsData : window.channelsData;
    if (!listElement || !Array.isArray(dataSource)) return;

    listElement.innerHTML = "";
    const groups = {};
    dataSource.forEach((ch, idx) => {
        const cat = ch.category || "Uncategorized";
        if (!groups[cat]) groups[cat] = [];
        groups[cat].push({ ...ch, originalIndex: idx });
    });

    for (const [groupName, groupChannels] of Object.entries(groups)) {
        const groupContainer = document.createElement("div");
        groupContainer.className = "group-container";

        const groupDiv = document.createElement("div");
        groupDiv.className = "group-title";
        groupDiv.innerText = `${groupName} (${groupChannels.length})`;
        groupDiv.onclick = function () {
            groupContainer.classList.toggle("collapsed");
        };

        groupContainer.appendChild(groupDiv);
        listElement.appendChild(groupContainer);

        const fragment = document.createDocumentFragment();
        for (let i = 0; i < groupChannels.length; i++) {
            const ch = groupChannels[i];
            const li = document.createElement("li");
            li.className = "channel-item";
            li.dataset.name = (ch.name || "").toLowerCase();

            const imgHtml = ch.logo
                ? `<img class="channel-logo" src="${ch.logo}" loading="lazy" onerror="this.style.display='none'">`
                : `<div class="channel-logo" style="display:flex; justify-content:center; align-items:center; font-size:1.2em;">TV</div>`;
            let tags = "";
            if (ch.useProxy) tags += '<span class="proxy-tag">Proxy</span>';
            if (ch.drmType === "widevine") tags += `<span class="drm-tag" style="right: ${ch.useProxy ? "85px" : "15px"}">WV</span>`;
            else if (ch.drmType === "playready") tags += `<span class="drm-tag" style="right: ${ch.useProxy ? "85px" : "15px"}">PR</span>`;

            li.innerHTML = imgHtml + `<span class="channel-name">${ch.name}</span>` + tags;
            li.onclick = () => playChannel(ch.originalIndex, li);
            fragment.appendChild(li);

            if (i > 0 && i % 60 === 0) {
                groupContainer.appendChild(fragment);
                await nextFrame();
            }
        }

        groupContainer.appendChild(fragment);
        await nextFrame();
    }
}

window.filterChannels = filterChannels;
window.renderChannelList = renderChannelList;

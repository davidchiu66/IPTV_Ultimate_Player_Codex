import json
import time
from typing import Any

from PySide6.QtCore import QObject, QEventLoop, QTimer, QUrl, Signal

from utils.url_cleaning import clean_media_url

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineUrlRequestInterceptor

    WEBENGINE_AVAILABLE = True
    WEBENGINE_ERROR = ""
except Exception as exc:  # pragma: no cover
    QWebEnginePage = None
    QWebEngineUrlRequestInterceptor = object
    WEBENGINE_AVAILABLE = False
    WEBENGINE_ERROR = str(exc)


_INSTALL_HOOKS_SCRIPT = r"""
(function() {
    if (window.__iptvProbeInstalled) {
        return true;
    }
    window.__iptvProbeInstalled = true;
    window.__iptvProbeState = {
        candidates: [],
        requests: [],
        errors: [],
        logs: [],
        sourceAssignments: [],
        lastUpdate: Date.now()
    };

    function touch() {
        try {
            window.__iptvProbeState.lastUpdate = Date.now();
        } catch (e) {}
    }

    function pushUnique(list, value) {
        if (!value || typeof value !== 'string') return;
        var clean = value.trim();
        if (!clean) return;
        if (list.indexOf(clean) === -1) {
            list.push(clean);
            touch();
        }
    }

    function recordCandidate(value) {
        try {
            pushUnique(window.__iptvProbeState.candidates, value);
        } catch (e) {}
    }

    function recordRequest(value) {
        try {
            pushUnique(window.__iptvProbeState.requests, value);
        } catch (e) {}
    }

    function recordLog(value) {
        try {
            pushUnique(window.__iptvProbeState.logs, value);
        } catch (e) {}
    }

    function recordError(code, message) {
        try {
            var payload = JSON.stringify({
                code: code || null,
                message: message || ''
            });
            pushUnique(window.__iptvProbeState.errors, payload);
        } catch (e) {}
    }

    function scanValue(value) {
        if (!value) return;
        if (typeof value === 'string') {
            recordCandidate(value);
            return;
        }
        if (Array.isArray(value)) {
            value.forEach(scanValue);
            return;
        }
        if (typeof value === 'object') {
            try {
                if (value.src) recordCandidate(value.src);
            } catch (e) {}
            try {
                if (value.url) recordCandidate(value.url);
            } catch (e) {}
            try {
                if (value.manifest) recordCandidate(value.manifest);
            } catch (e) {}
            try {
                if (value.playUrl) recordCandidate(value.playUrl);
            } catch (e) {}
            try {
                if (value.liveUrl) recordCandidate(value.liveUrl);
            } catch (e) {}
        }
    }

    function resolveMediaCandidate(value, baseUrl) {
        if (!value || typeof value !== 'string') return '';
        var clean = value.trim();
        if (!clean) return '';
        try {
            if (clean.indexOf('//') === 0) {
                clean = location.protocol + clean;
            } else if (
                clean.indexOf('http://') !== 0 &&
                clean.indexOf('https://') !== 0 &&
                (clean.charAt(0) === '/' || clean.indexOf('./') === 0 || clean.indexOf('../') === 0)
            ) {
                clean = new URL(clean, baseUrl || location.href).href;
            }
        } catch (e) {}
        return clean;
    }

    function scanTextForMedia(text, baseUrl) {
        if (!text || typeof text !== 'string') return;
        var sample = text.length > 1048576 ? text.slice(0, 1048576) : text;
        var patterns = [
            /https?:\/\/[^\s'"<>]+(?:\.m3u8|\.mpd|\.flv|\.mp4|\.ts|\.m4s)(?:\?[^\s'"<>]*)?/ig,
            /(?:^|[\s"'(])((?:\/\/|\/|\.\/|\.\.\/)?[^\s"'()<>]+(?:\.m3u8|\.mpd|\.flv|\.mp4|\.ts|\.m4s)(?:\?[^\s"'()<>]*)?)/ig
        ];
        patterns.forEach(function(pattern) {
            var match;
            while ((match = pattern.exec(sample)) !== null) {
                var value = match[1] || match[0] || '';
                recordCandidate(resolveMediaCandidate(value, baseUrl));
            }
        });
    }

    function shouldScanResponseText(url, contentType) {
        var lower = String((url || '') + ' ' + (contentType || '')).toLowerCase();
        return (
            lower.indexOf('.m3u8') !== -1 ||
            lower.indexOf('.mpd') !== -1 ||
            lower.indexOf('play.php') !== -1 ||
            lower.indexOf('manifest') !== -1 ||
            lower.indexOf('playlist') !== -1 ||
            lower.indexOf('mpegurl') !== -1 ||
            lower.indexOf('text/') !== -1 ||
            lower.indexOf('json') !== -1 ||
            lower.indexOf('javascript') !== -1
        );
    }

    try {
        var originalFetch = window.fetch;
        if (typeof originalFetch === 'function') {
            window.fetch = function() {
                var requestUrl = '';
                try {
                    if (arguments.length > 0) {
                        var input = arguments[0];
                        if (typeof input === 'string') {
                            requestUrl = input;
                        } else if (input && input.url) {
                            requestUrl = input.url;
                        }
                        recordRequest(requestUrl);
                        recordCandidate(requestUrl);
                    }
                } catch (e) {}
                var result = originalFetch.apply(this, arguments);
                try {
                    if (result && typeof result.then === 'function') {
                        return result.then(function(response) {
                            try {
                                var finalUrl = response && response.url ? response.url : '';
                                if (finalUrl) {
                                    recordRequest(finalUrl);
                                    recordCandidate(finalUrl);
                                    recordLog('fetch-response-url=' + finalUrl);
                                }
                                var contentType = '';
                                try {
                                    contentType = response && response.headers ? (response.headers.get('content-type') || '') : '';
                                } catch (e) {}
                                if (response && response.clone && shouldScanResponseText(finalUrl || requestUrl, contentType)) {
                                    try {
                                        response.clone().text().then(function(text) {
                                            scanTextForMedia(text, finalUrl || requestUrl || location.href);
                                        }).catch(function() {});
                                    } catch (e) {}
                                }
                            } catch (e) {}
                            return response;
                        });
                    }
                } catch (e) {}
                return result;
            };
        }
    } catch (e) {}

    try {
        var originalOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url) {
            try {
                this.__iptvProbeUrl = url;
                recordRequest(url);
                recordCandidate(url);
                if (!this.__iptvProbeLoadEndHooked) {
                    this.__iptvProbeLoadEndHooked = true;
                    this.addEventListener('loadend', function() {
                        try {
                            var finalUrl = this.responseURL || this.__iptvProbeUrl || '';
                            if (finalUrl) {
                                recordRequest(finalUrl);
                                recordCandidate(finalUrl);
                                recordLog('xhr-response-url=' + finalUrl);
                            }
                            var contentType = '';
                            try {
                                contentType = this.getResponseHeader ? (this.getResponseHeader('content-type') || '') : '';
                            } catch (e) {}
                            if (shouldScanResponseText(finalUrl, contentType)) {
                                try {
                                    scanTextForMedia(this.responseText || '', finalUrl || location.href);
                                } catch (e) {}
                            }
                        } catch (e) {}
                    });
                }
            } catch (e) {}
            return originalOpen.apply(this, arguments);
        };
    } catch (e) {}

    try {
        var originalSetAttribute = Element.prototype.setAttribute;
        Element.prototype.setAttribute = function(name, value) {
            try {
                if (name && typeof name === 'string') {
                    var key = name.toLowerCase();
                    if (key === 'src' || key === 'data-src' || key === 'href') {
                        recordCandidate(value);
                    }
                }
            } catch (e) {}
            return originalSetAttribute.apply(this, arguments);
        };
    } catch (e) {}

    try {
        var desc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
        if (desc && desc.set) {
            Object.defineProperty(HTMLMediaElement.prototype, 'src', {
                configurable: true,
                enumerable: desc.enumerable,
                get: function() {
                    return desc.get ? desc.get.call(this) : '';
                },
                set: function(value) {
                    try {
                        recordCandidate(value);
                    } catch (e) {}
                    return desc.set.call(this, value);
                }
            });
        }
    } catch (e) {}

    try {
        var originalCreateElement = document.createElement;
        document.createElement = function(tagName) {
            var element = originalCreateElement.apply(this, arguments);
            try {
                if (String(tagName || '').toLowerCase() === 'video') {
                    element.addEventListener('error', function() {
                        try {
                            var err = element.error || {};
                            recordError(err.code || null, err.message || '');
                        } catch (e) {}
                    }, true);
                }
            } catch (e) {}
            return element;
        };
    } catch (e) {}

    try {
        document.addEventListener('error', function(event) {
            try {
                var target = event && event.target;
                if (target && target.tagName && String(target.tagName).toLowerCase() === 'video') {
                    var err = target.error || {};
                    recordError(err.code || null, err.message || '');
                }
            } catch (e) {}
        }, true);
    } catch (e) {}

    try {
        var installVideoJsHook = function() {
            try {
                if (!window.videojs || window.videojs.__iptvProbeWrapped) {
                    return;
                }
                window.videojs.__iptvProbeWrapped = true;
                var originalVideoJs = window.videojs;

                function wrapPlayer(player) {
                    if (!player || player.__iptvProbeWrapped) {
                        return player;
                    }
                    player.__iptvProbeWrapped = true;
                    try {
                        if (typeof player.src === 'function') {
                            var originalSrc = player.src;
                            player.src = function(value) {
                                try {
                                    scanValue(value);
                                    window.__iptvProbeState.sourceAssignments.push(JSON.stringify(value));
                                    touch();
                                } catch (e) {}
                                return originalSrc.apply(this, arguments);
                            };
                        }
                    } catch (e) {}
                    try {
                        if (typeof player.currentSource === 'function') {
                            scanValue(player.currentSource());
                        }
                    } catch (e) {}
                    try {
                        if (typeof player.currentSources === 'function') {
                            scanValue(player.currentSources());
                        }
                    } catch (e) {}
                    try {
                        if (typeof player.on === 'function') {
                            player.on('error', function() {
                                try {
                                    var err = player.error ? player.error() : null;
                                    if (err) {
                                        recordError(err.code || null, err.message || '');
                                    }
                                } catch (e) {}
                            });
                        }
                    } catch (e) {}
                    return player;
                }

                if (typeof originalVideoJs === 'function') {
                    var wrappedVideoJs = function() {
                        var player = originalVideoJs.apply(this, arguments);
                        return wrapPlayer(player);
                    };
                    Object.keys(originalVideoJs).forEach(function(key) {
                        try {
                            wrappedVideoJs[key] = originalVideoJs[key];
                        } catch (e) {}
                    });
                    wrappedVideoJs.__iptvProbeWrapped = true;
                    window.videojs = wrappedVideoJs;
                }

                try {
                    var players = originalVideoJs.getPlayers ? originalVideoJs.getPlayers() : {};
                    Object.keys(players || {}).forEach(function(key) {
                        wrapPlayer(players[key]);
                    });
                } catch (e) {}
            } catch (e) {}
        };

        installVideoJsHook();
        setInterval(installVideoJsHook, 500);
    } catch (e) {}

    try {
        var installStreamingHooks = function() {
            try {
                if (window.Hls && window.Hls.prototype && !window.Hls.prototype.__iptvProbeWrapped) {
                    window.Hls.prototype.__iptvProbeWrapped = true;
                    if (typeof window.Hls.prototype.loadSource === 'function') {
                        var originalLoadSource = window.Hls.prototype.loadSource;
                        window.Hls.prototype.loadSource = function(url) {
                            try {
                                recordCandidate(url);
                                recordLog('hls-loadSource=' + url);
                            } catch (e) {}
                            return originalLoadSource.apply(this, arguments);
                        };
                    }
                }
            } catch (e) {}

            try {
                if (window.mpegts && typeof window.mpegts.createPlayer === 'function' && !window.mpegts.__iptvProbeWrapped) {
                    window.mpegts.__iptvProbeWrapped = true;
                    var originalCreatePlayer = window.mpegts.createPlayer;
                    window.mpegts.createPlayer = function(config) {
                        try {
                            scanValue(config);
                            if (config && config.url) {
                                recordCandidate(config.url);
                                recordLog('mpegts-createPlayer=' + config.url);
                            }
                        } catch (e) {}
                        return originalCreatePlayer.apply(this, arguments);
                    };
                }
            } catch (e) {}
        };

        installStreamingHooks();
        setInterval(installStreamingHooks, 500);
    } catch (e) {}

    try {
        var observer = new MutationObserver(function() {
            try {
                Array.from(document.querySelectorAll('video, source')).forEach(function(node) {
                    try {
                        if (node.currentSrc) recordCandidate(node.currentSrc);
                    } catch (e) {}
                    try {
                        if (node.src) recordCandidate(node.src);
                    } catch (e) {}
                    try {
                        if (node.getAttribute) recordCandidate(node.getAttribute('src') || '');
                    } catch (e) {}
                });
            } catch (e) {}
        });
        observer.observe(document.documentElement || document, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['src', 'href', 'data-src']
        });
    } catch (e) {}

    recordLog('probe-hooks-installed');
    return true;
})();
"""

_SNAPSHOT_SCRIPT = r"""
(function() {
    function normalize(value) {
        if (!value || typeof value !== 'string') return '';
        return value.trim();
    }

    function add(list, value) {
        var clean = normalize(value);
        if (!clean) return;
        if (list.indexOf(clean) === -1) {
            list.push(clean);
        }
    }

    function looksLikeUrl(text) {
        var clean = normalize(text);
        if (!clean) return false;
        var lower = clean.toLowerCase();
        if (lower.indexOf('http://') === 0 || lower.indexOf('https://') === 0 || lower.indexOf('//') === 0) {
            return true;
        }
        if (lower.indexOf('/api/') === 0) {
            return true;
        }
        if (
            lower.indexOf('.m3u8') !== -1 ||
            lower.indexOf('.mpd') !== -1 ||
            lower.indexOf('.flv') !== -1 ||
            lower.indexOf('.mp4') !== -1 ||
            lower.indexOf('.ts') !== -1 ||
            lower.indexOf('.m4s') !== -1
        ) {
            return true;
        }
        return false;
    }

    function looksInterestingKey(key) {
        var lower = String(key || '').toLowerCase();
        return (
            lower.indexOf('play') !== -1 ||
            lower.indexOf('live') !== -1 ||
            lower.indexOf('video') !== -1 ||
            lower.indexOf('media') !== -1 ||
            lower.indexOf('stream') !== -1 ||
            lower.indexOf('source') !== -1 ||
            lower.indexOf('manifest') !== -1 ||
            lower.indexOf('playlist') !== -1 ||
            lower.indexOf('url') !== -1 ||
            lower.indexOf('channel') !== -1
        );
    }

    function collectRegexCandidates(text, out) {
        if (!text || typeof text !== 'string') return;
        var patterns = [
            /https?:\/\/[^\s'"<>]+(?:\.m3u8|\.mpd|\.flv|\.mp4|\.ts|\.m4s)(?:\?[^\s'"<>]*)?/ig,
            /https?:\/\/[^\s'"<>]+(?:manifest|playlist|stream|play|live|media|video)[^\s'"<>]*/ig,
            /["']((?:\/|https?:\/\/)[^"'<>]*(?:manifest|playlist|stream|play|live|media|video|api)[^"'<>]*)["']/ig
        ];
        patterns.forEach(function(pattern) {
            var match;
            while ((match = pattern.exec(text)) !== null) {
                add(out, match[1] || match[0] || '');
            }
        });
    }

    function collectObjectValues(value, out, depth, visited, budget) {
        if (!value || budget.count > 600) return;
        if (depth > 4) return;
        if (typeof value === 'string') {
            if (looksLikeUrl(value) || /manifest|playlist|stream|play|live|media|video/i.test(value)) {
                add(out, value);
            }
            return;
        }
        if (typeof value !== 'object') return;
        if (visited.indexOf(value) !== -1) return;
        visited.push(value);
        budget.count += 1;

        if (Array.isArray(value)) {
            value.slice(0, 80).forEach(function(item) {
                collectObjectValues(item, out, depth + 1, visited, budget);
            });
            return;
        }

        Object.keys(value).slice(0, 80).forEach(function(key) {
            var child;
            try {
                child = value[key];
            } catch (e) {
                return;
            }
            if (looksInterestingKey(key)) {
                if (typeof child === 'string') {
                    add(out, child);
                    collectRegexCandidates(child, out);
                } else {
                    collectObjectValues(child, out, depth + 1, visited, budget);
                }
            } else if (depth < 2) {
                collectObjectValues(child, out, depth + 1, visited, budget);
            }
        });
    }

    function collectWindowObjectCandidates() {
        var candidates = [];
        var visited = [];
        var budget = { count: 0 };
        var seedKeys = [
            '__INITIAL_STATE__',
            '__NEXT_DATA__',
            '__NUXT__',
            '__APOLLO_STATE__',
            '__data__',
            '__DATA__',
            '__PLAYER_CONFIG__',
            '__PLAY_INFO__',
            'videojs',
            'player',
            'players',
            'playerOptions',
            'playerConfig',
            'playInfo',
            'playData',
            'liveInfo',
            'liveData',
            'channelInfo',
            'channelData'
        ];

        seedKeys.forEach(function(key) {
            try {
                if (window[key]) {
                    collectObjectValues(window[key], candidates, 0, visited, budget);
                }
            } catch (e) {}
        });

        try {
            Object.keys(window).slice(0, 300).forEach(function(key) {
                try {
                    if (looksInterestingKey(key)) {
                        collectObjectValues(window[key], candidates, 0, visited, budget);
                    }
                } catch (e) {}
            });
        } catch (e) {}

        return candidates;
    }

    function collectInlineScriptCandidates() {
        var candidates = [];
        try {
            Array.from(document.querySelectorAll('script')).forEach(function(script) {
                try {
                    add(candidates, script.src || '');
                    collectRegexCandidates(script.textContent || '', candidates);
                } catch (e) {}
            });
        } catch (e) {}
        return candidates;
    }

    function collectAttributeCandidates() {
        var candidates = [];
        try {
            Array.from(document.querySelectorAll('[src],[href],[data-src],[poster]')).forEach(function(node) {
                try { add(candidates, node.getAttribute('src') || ''); } catch (e) {}
                try { add(candidates, node.getAttribute('href') || ''); } catch (e) {}
                try { add(candidates, node.getAttribute('data-src') || ''); } catch (e) {}
                try { add(candidates, node.getAttribute('poster') || ''); } catch (e) {}
            });
        } catch (e) {}
        return candidates;
    }

    function collectDomRegexCandidates() {
        var candidates = [];
        try {
            collectRegexCandidates((document.documentElement && document.documentElement.outerHTML) || '', candidates);
        } catch (e) {}
        try {
            collectRegexCandidates((document.body && document.body.innerHTML) || '', candidates);
        } catch (e) {}
        return candidates;
    }

    function collectDirectDomMediaCandidates() {
        var candidates = [];
        var selectors = [
            'video',
            'source',
            'video source',
            '#video',
            '#video_html5_api',
            '#video source',
            '#video_html5_api source'
        ];

        function collectNode(node) {
            if (!node) return;
            try { add(candidates, node.currentSrc || ''); } catch (e) {}
            try { add(candidates, node.src || ''); } catch (e) {}
            try { add(candidates, node.getAttribute ? (node.getAttribute('src') || '') : ''); } catch (e) {}
            try { add(candidates, node.getAttribute ? (node.getAttribute('data-src') || '') : ''); } catch (e) {}
            try {
                Array.from(node.querySelectorAll ? node.querySelectorAll('source') : []).forEach(collectNode);
            } catch (e) {}
        }

        selectors.forEach(function(selector) {
            try {
                Array.from(document.querySelectorAll(selector)).forEach(collectNode);
            } catch (e) {}
        });

        try {
            Array.from(document.querySelectorAll('source')).forEach(function(source) {
                var type = '';
                try { type = String(source.getAttribute('type') || '').toLowerCase(); } catch (e) {}
                if (
                    type.indexOf('mpegurl') !== -1 ||
                    type.indexOf('dash') !== -1 ||
                    type.indexOf('mp4') !== -1 ||
                    type.indexOf('flv') !== -1
                ) {
                    collectNode(source);
                }
            });
        } catch (e) {}

        return candidates;
    }

    function collectDecodedPlayerCandidates() {
        var candidates = [];
        try {
            if (typeof window.yvdtd !== 'function') {
                return candidates;
            }
            Array.from(document.querySelectorAll('#playURL option, select option')).slice(0, 40).forEach(function(option) {
                var value = '';
                try { value = option.value || option.getAttribute('value') || ''; } catch (e) {}
                if (!value) return;
                try {
                    var decoded = window.yvdtd(value);
                    add(candidates, decoded || '');
                    collectRegexCandidates(decoded || '', candidates);
                } catch (e) {}
            });
        } catch (e) {}
        return candidates;
    }

    function collectSources() {
        var candidates = [];

        collectDecodedPlayerCandidates().forEach(function(item) { add(candidates, item); });
        collectDirectDomMediaCandidates().forEach(function(item) { add(candidates, item); });

        Array.from(document.querySelectorAll('video')).forEach(function(video) {
            try { add(candidates, video.currentSrc || ''); } catch (e) {}
            try { add(candidates, video.src || ''); } catch (e) {}
            try {
                Array.from(video.querySelectorAll('source')).forEach(function(source) {
                    add(candidates, source.src || '');
                });
            } catch (e) {}
        });

        if (window.videojs && typeof window.videojs.getPlayers === 'function') {
            try {
                var players = window.videojs.getPlayers();
                Object.keys(players || {}).forEach(function(key) {
                    var player = players[key];
                    if (!player) return;
                    try {
                        var currentSource = player.currentSource ? player.currentSource() : null;
                        if (currentSource) add(candidates, currentSource.src || '');
                    } catch (e) {}
                    try {
                        var currentSources = player.currentSources ? player.currentSources() : [];
                        (currentSources || []).forEach(function(source) {
                            if (source) add(candidates, source.src || '');
                        });
                    } catch (e) {}
                    try {
                        add(candidates, player.src ? player.src() : '');
                    } catch (e) {}
                    try {
                        collectObjectValues(player.options_ || null, candidates, 0, [], { count: 0 });
                    } catch (e) {}
                    try {
                        collectObjectValues(player.cache_ || null, candidates, 0, [], { count: 0 });
                    } catch (e) {}
                    try {
                        collectObjectValues(player.mediainfo || null, candidates, 0, [], { count: 0 });
                    } catch (e) {}
                    try {
                        collectObjectValues(player.tech_ || null, candidates, 0, [], { count: 0 });
                    } catch (e) {}
                });
            } catch (e) {}
        }

        try {
            var probeState = window.__iptvProbeState || {};
            (probeState.candidates || []).forEach(function(item) { add(candidates, item); });
        } catch (e) {}

        collectInlineScriptCandidates().forEach(function(item) { add(candidates, item); });
        collectAttributeCandidates().forEach(function(item) { add(candidates, item); });
        collectDomRegexCandidates().forEach(function(item) { add(candidates, item); });
        collectWindowObjectCandidates().forEach(function(item) { add(candidates, item); });

        return candidates;
    }

    function collectErrors() {
        var errors = [];
        function pushError(code, message) {
            errors.push({
                code: code || null,
                message: message || ''
            });
        }

        Array.from(document.querySelectorAll('video')).forEach(function(video) {
            try {
                if (video && video.error) {
                    pushError(video.error.code || null, video.error.message || '');
                }
            } catch (e) {}
        });

        if (window.videojs && typeof window.videojs.getPlayers === 'function') {
            try {
                var players = window.videojs.getPlayers();
                Object.keys(players || {}).forEach(function(key) {
                    var player = players[key];
                    if (!player) return;
                    try {
                        var err = player.error ? player.error() : null;
                        if (err) {
                            pushError(err.code || null, err.message || '');
                        }
                    } catch (e) {}
                });
            } catch (e) {}
        }

        try {
            var probeState = window.__iptvProbeState || {};
            (probeState.errors || []).forEach(function(item) {
                try {
                    var data = JSON.parse(item);
                    pushError(data.code || null, data.message || '');
                } catch (e) {}
            });
        } catch (e) {}

        return errors;
    }

    function collectRequests() {
        var requests = [];
        try {
            var probeState = window.__iptvProbeState || {};
            (probeState.requests || []).forEach(function(item) { add(requests, item); });
        } catch (e) {}
        return requests;
    }

    function collectLogs() {
        var logs = [];
        try {
            var probeState = window.__iptvProbeState || {};
            (probeState.logs || []).forEach(function(item) { add(logs, item); });
            (probeState.sourceAssignments || []).forEach(function(item) { add(logs, 'src=' + item); });
        } catch (e) {}
        return logs;
    }

    return JSON.stringify({
        url: location.href,
        title: document.title || '',
        readyState: document.readyState || '',
        candidates: collectSources(),
        requests: collectRequests(),
        errors: collectErrors(),
        logs: collectLogs(),
        timestamp: Date.now()
    });
})();
"""

_ACTIVATE_MEDIA_SCRIPT = r"""
(function() {
    try {
        window.__iptvProbeActivationCount = (window.__iptvProbeActivationCount || 0) + 1;
        if (window.__iptvProbeActivationCount > 60) {
            return true;
        }
        var state = window.__iptvProbeState || null;
        function log(value) {
            try {
                if (!state || !state.logs) return;
                if (state.logs.indexOf(value) === -1) {
                    state.logs.push(value);
                }
            } catch (e) {}
        }
        function candidate(value) {
            try {
                if (!value || !state || !state.candidates) return;
                value = String(value).trim();
                if (value && state.candidates.indexOf(value) === -1) {
                    state.candidates.push(value);
                    state.lastUpdate = Date.now();
                }
            } catch (e) {}
        }

        try {
            var select = document.querySelector('#playURL') || document.querySelector('select');
            var now = Date.now();
            var shouldSwitchLine = !window.__iptvProbeLastLineSwitchAt || (now - window.__iptvProbeLastLineSwitchAt >= 4500);
            if (select && shouldSwitchLine) {
                var options = Array.from(select.options || []);
                var selectedIndex = select.selectedIndex >= 0 ? select.selectedIndex : 0;
                var lineIndex = typeof window.__iptvProbeNextLineIndex === 'number' ? window.__iptvProbeNextLineIndex : selectedIndex;
                if (options.length > 0) {
                    lineIndex = Math.max(0, Math.min(lineIndex, options.length - 1));
                    select.selectedIndex = lineIndex;
                    window.__iptvProbeNextLineIndex = (lineIndex + 1) % options.length;
                }
                var value = select.value || '';
                if (value && typeof window.yvdtd === 'function') {
                    try { candidate(window.yvdtd(value)); } catch (e) {}
                }
                if (value && typeof window.wphct === 'function') {
                    window.wphct(value);
                    log('called-wphct-line=' + lineIndex);
                } else {
                    try {
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                        log('dispatched-select-change-line=' + lineIndex);
                    } catch (e) {}
                }
                window.__iptvProbeLastLineSwitchAt = now;
            } else if (!select && shouldSwitchLine) {
                window.__iptvProbeLastLineSwitchAt = now;
            }
        } catch (e) {}

        var selectors = [
            '.vjs-big-play-button',
            '.video-js button',
            'button[title*="Play"]',
            'button[aria-label*="Play"]',
            'button[class*="play"]',
            '[class*="play"]',
            '#play',
            '#vstPlayer',
            'video'
        ];
        selectors.forEach(function(selector) {
            try {
                Array.from(document.querySelectorAll(selector)).slice(0, 4).forEach(function(node) {
                    try { node.click(); log('clicked=' + selector); } catch (e) {}
                });
            } catch (e) {}
        });

        try {
            Array.from(document.querySelectorAll('video')).forEach(function(video) {
                try { video.muted = true; } catch (e) {}
                try {
                    var result = video.play && video.play();
                    if (result && result.catch) {
                        result.catch(function() {});
                    }
                } catch (e) {}
            });
        } catch (e) {}
    } catch (e) {}
    return true;
})();
"""

_STRONG_MEDIA_TOKENS = (".m3u8", ".mpd", ".flv", ".mp4", ".ts", ".m4s")
_WEAK_MEDIA_TOKENS = (
    "manifest",
    "playlist",
    "stream",
    "play",
    "live",
    "channel",
    "media",
    "video",
)
_STATIC_RESOURCE_TOKENS = (
    ".js",
    ".css",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".map",
    "q_stat.php",
)
_PAGE_PATH_TOKENS = (
    "/channeldetail/",
    "/tvchanneldetail/",
    "/tvcolumn/",
    "/article/",
    "/node_",
)
_POLL_INTERVAL_MS = 1000
_DEFAULT_TIMEOUT_MS = 30000


class _MediaRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def interceptRequest(self, info):  # pragma: no cover - Qt callback
        try:
            url = info.requestUrl().toString()
            resource_type = int(info.resourceType())
        except Exception:
            return
        self.owner._register_network_request(url, resource_type)


class BrowserProbeSession(QObject):
    progress = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = None
        self._profile = None
        self._interceptor = None
        self._candidates: list[str] = []
        self._requests: list[str] = []
        self._console_messages: list[str] = []
        self._library_source_types: dict[str, str] = {}
        self._page_snapshot: dict[str, Any] = {}
        self._page_loaded = False
        self._saw_player_error = False
        self._best_candidate_seen_at = 0.0
        self._probe_started_at = 0.0
        self._timed_out = False

    def _register_candidate(self, url: str):
        clean = clean_media_url(url)
        if not clean or clean in self._candidates:
            return
        self._candidates.append(clean)
        self._best_candidate_seen_at = time.monotonic()
        self.progress.emit(f"已捕获媒体候选：{clean}")

    def _looks_like_static_resource(self, url: str) -> bool:
        lower = str(url or "").lower()
        return any(token in lower for token in _STATIC_RESOURCE_TOKENS)

    def _record_library_source(self, source_type: str, url: str):
        clean = clean_media_url(url)
        if not clean:
            return
        normalized_type = str(source_type or "unknown").strip().lower() or "unknown"
        self._library_source_types[clean.lower()] = normalized_type
        self._register_candidate(clean)

    def _library_source_type(self, url: str) -> str:
        return self._library_source_types.get(str(url or "").strip().lower(), "")

    def _candidate_confidence(self, url: str) -> str:
        lower = str(url or "").lower()
        if not lower:
            return "none"
        if lower.startswith("videojs:"):
            return "none"
        if self._library_source_type(url):
            if ".php" in lower and not any(token in lower for token in _STRONG_MEDIA_TOKENS):
                return "low"
            return "high"
        if any(token in lower for token in _STRONG_MEDIA_TOKENS):
            return "high"
        if self._looks_like_static_resource(lower):
            return "none"
        if any(token in lower for token in _PAGE_PATH_TOKENS):
            return "none"
        if lower.startswith("/") and not any(token in lower for token in _STRONG_MEDIA_TOKENS):
            return "none"
        if lower.startswith("http://") or lower.startswith("https://"):
            if any(token in lower for token in ("manifest", "playlist", "stream")):
                return "medium"
            if any(token in lower for token in ("play", "live", "media", "video")):
                return "low"
        if any(token in lower for token in _WEAK_MEDIA_TOKENS):
            return "low"
        return "none"

    def _looks_like_media_candidate(self, url: str) -> bool:
        return self._candidate_confidence(url) != "none"

    def _is_playable_candidate(self, url: str) -> bool:
        return self._candidate_confidence(url) in {"high", "medium"}

    def _has_playable_candidate(self) -> bool:
        return any(self._is_playable_candidate(item) for item in self._candidates)

    def _register_network_request(self, url: str, _resource_type: int):
        clean = clean_media_url(url)
        if not clean:
            return
        if clean not in self._requests:
            self._requests.append(clean)
        if self._looks_like_media_candidate(clean):
            self._register_candidate(clean)

    def _sort_candidates(self):
        def sort_key(url: str):
            lower = url.lower()
            confidence = self._candidate_confidence(url)
            if confidence == "high":
                base = 0
            elif confidence == "medium":
                base = 20
            elif confidence == "low":
                base = 40
            else:
                base = 90
            if ".mpd" in lower:
                return (base + 0, len(url))
            if ".m3u8" in lower:
                return (base + 1, len(url))
            if ".m4s" in lower:
                return (base + 2, len(url))
            if ".ts" in lower:
                return (base + 3, len(url))
            if ".flv" in lower:
                return (base + 4, len(url))
            if ".mp4" in lower:
                return (base + 5, len(url))
            if "manifest" in lower:
                return (base + 6, len(url))
            if "playlist" in lower:
                return (base + 7, len(url))
            if "stream" in lower:
                return (base + 8, len(url))
            if "live" in lower:
                return (base + 9, len(url))
            if "media" in lower:
                return (base + 11, len(url))
            if "video" in lower:
                return (base + 12, len(url))
            if "play" in lower:
                return (base + 13, len(url))
            return (base + 19, len(url))

        self._candidates.sort(key=sort_key)

    def _merge_snapshot(self, data: dict[str, Any]):
        self._page_snapshot = data
        for item in data.get("requests") or []:
            if isinstance(item, str):
                self._register_network_request(item, 0)
        for item in data.get("candidates") or []:
            if isinstance(item, str) and self._looks_like_media_candidate(item):
                self._register_candidate(item)
        for item in data.get("logs") or []:
            if isinstance(item, str):
                self._console_messages.append(item)
                if item.startswith("hls-loadSource="):
                    self._record_library_source("hls", item.partition("=")[2])
                elif item.startswith("mpegts-createPlayer="):
                    self._record_library_source("flv", item.partition("=")[2])
        for err in data.get("errors") or []:
            try:
                code = err.get("code")
                msg = err.get("message") or ""
                if code or msg:
                    self._saw_player_error = True
                    self._console_messages.append(f"player-error code={code} message={msg}")
            except Exception:
                pass

    def _install_probe_hooks(self):
        if self._page is None:
            return
        try:
            self._page.runJavaScript(_INSTALL_HOOKS_SCRIPT)
        except Exception:
            pass

    def _activate_media_playback(self):
        if self._page is None:
            return
        try:
            self._page.runJavaScript(_ACTIVATE_MEDIA_SCRIPT)
        except Exception:
            pass

    def _run_js_snapshot(self, callback=None):
        if self._page is None:
            if callback:
                callback(False)
            return

        def _handle_result(raw):
            changed = False
            if raw:
                try:
                    data = json.loads(str(raw))
                except Exception:
                    data = None
                if isinstance(data, dict):
                    before_candidates = len(self._candidates)
                    before_requests = len(self._requests)
                    before_logs = len(self._console_messages)
                    self._merge_snapshot(data)
                    changed = (
                        len(self._candidates) != before_candidates
                        or len(self._requests) != before_requests
                        or len(self._console_messages) != before_logs
                    )
            if callback:
                callback(changed)

        try:
            self._page.runJavaScript(_SNAPSHOT_SCRIPT, _handle_result)
        except Exception:
            if callback:
                callback(False)

    def _run_js_snapshot_sync(self, timeout_ms: int = 1500):
        if self._page is None:
            return

        loop = QEventLoop(self)
        guard_timer = QTimer(self)
        guard_timer.setSingleShot(True)

        def _finish(_changed=False):
            try:
                guard_timer.stop()
            except Exception:
                pass
            if loop.isRunning():
                loop.quit()

        guard_timer.timeout.connect(_finish)
        guard_timer.start(timeout_ms)
        self._run_js_snapshot(_finish)
        loop.exec()

    def _best_result(self, elapsed_ms: int) -> dict[str, Any]:
        self._sort_candidates()
        playable_candidates = [item for item in self._candidates if self._is_playable_candidate(item)]
        if playable_candidates:
            first = playable_candidates[0]
            library_type = self._library_source_type(first)
            media_type = (
                "dash"
                if ".mpd" in first.lower()
                else "hls"
                if ".m3u8" in first.lower()
                else library_type
                if library_type
                else "unknown"
            )
            return {
                "status": "ok",
                "message": "resolved from browser probe",
                "media_url": first,
                "media_type": media_type,
                "candidates": list(self._candidates),
                "playable_candidates": playable_candidates,
                "requests": list(self._requests),
                "console": list(self._console_messages[-30:]),
                "snapshot": dict(self._page_snapshot),
                "elapsed_ms": elapsed_ms,
                "timed_out": bool(self._timed_out),
                "page_url": (self._page_snapshot or {}).get("url") or "",
            }

        detail = "browser probe timed out without capturing playable media"
        snapshot_candidates = (self._page_snapshot or {}).get("candidates") or []
        snapshot_requests = (self._page_snapshot or {}).get("requests") or []
        if self._candidates or snapshot_candidates:
            detail = "browser probe captured page sources but none looked like playable media"
        elif snapshot_requests or self._requests:
            detail = "browser probe saw page requests but no playable media url"
        elif self._saw_player_error or self._console_messages:
            detail = "browser probe saw player errors but no playable media url"

        return {
            "status": "page",
            "message": detail,
            "candidates": list(self._candidates),
            "playable_candidates": playable_candidates,
            "requests": list(self._requests),
            "console": list(self._console_messages[-30:]),
            "snapshot": dict(self._page_snapshot),
            "elapsed_ms": elapsed_ms,
            "timed_out": bool(self._timed_out),
            "page_url": (self._page_snapshot or {}).get("url") or "",
        }

    def probe_channel(self, channel: dict[str, Any], timeout_ms: int = _DEFAULT_TIMEOUT_MS) -> dict[str, Any]:
        if not WEBENGINE_AVAILABLE:
            return {
                "status": "error",
                "message": f"Qt WebEngine unavailable: {WEBENGINE_ERROR}",
                "candidates": [],
            }

        manifest = str((channel or {}).get("Manifest") or "").strip()
        if not manifest:
            return {"status": "error", "message": "missing manifest url", "candidates": []}

        self.progress.emit("正在启动受控浏览器探测...")
        self._page = QWebEnginePage(self)
        self._profile = self._page.profile()
        self._interceptor = _MediaRequestInterceptor(self)
        self._profile.setUrlRequestInterceptor(self._interceptor)
        self._candidates = []
        self._requests = []
        self._console_messages = []
        self._library_source_types = {}
        self._page_snapshot = {}
        self._page_loaded = False
        self._saw_player_error = False
        self._best_candidate_seen_at = 0.0
        self._probe_started_at = time.monotonic()
        self._timed_out = False

        original_console = self._page.javaScriptConsoleMessage

        def console_hook(level, message, line_number, source_id):  # pragma: no cover - Qt callback
            try:
                text = f"{message}"
                self._console_messages.append(text)
                lower = text.lower()
                if "media_err" in lower or "src_not_supported" in lower or "player-error" in lower:
                    self._saw_player_error = True
                for token in text.split():
                    stripped = token.strip(' "\'(),;')
                    if self._is_playable_candidate(stripped):
                        self._register_candidate(stripped)
            except Exception:
                pass
            try:
                original_console(level, message, line_number, source_id)
            except Exception:
                pass

        self._page.javaScriptConsoleMessage = console_hook

        loop = QEventLoop(self)
        timeout_timer = QTimer(self)
        timeout_timer.setSingleShot(True)

        def on_timeout():
            self._timed_out = True
            loop.quit()

        timeout_timer.timeout.connect(on_timeout)

        poll_timer = QTimer(self)
        poll_timer.setInterval(_POLL_INTERVAL_MS)
        poll_timer.timeout.connect(self._install_probe_hooks)
        poll_timer.timeout.connect(self._activate_media_playback)
        poll_timer.timeout.connect(self._run_js_snapshot)

        settle_timer = QTimer(self)
        settle_timer.setSingleShot(True)
        settle_timer.timeout.connect(loop.quit)

        def on_load_finished(_ok):
            self._page_loaded = True
            self.progress.emit("页面已加载，正在持续探测真实播放地址...")
            self._install_probe_hooks()
            self._activate_media_playback()
            self._run_js_snapshot()
            if not poll_timer.isActive():
                poll_timer.start()

        def on_load_started():
            self.progress.emit("正在加载页面并监听媒体请求...")
            self._install_probe_hooks()
            self._activate_media_playback()

        def on_poll():
            if self._has_playable_candidate():
                self.progress.emit("已发现候选媒体地址，正在确认可播放来源...")
                if not settle_timer.isActive():
                    settle_timer.start(1200)
            elif self._page_loaded:
                elapsed = int((time.monotonic() - self._probe_started_at) * 1000)
                remaining = max(0, timeout_ms - elapsed)
                self.progress.emit(f"页面已加载，继续探测中... 剩余 {max(1, remaining // 1000)}s")

        poll_timer.timeout.connect(on_poll)
        self._page.loadStarted.connect(on_load_started)
        self._page.loadFinished.connect(on_load_finished)

        timeout_timer.start(timeout_ms)
        self.progress.emit("正在加载页面并监听媒体请求...")
        self._page.load(QUrl(manifest))
        loop.exec()

        poll_timer.stop()
        settle_timer.stop()
        timeout_timer.stop()
        self._run_js_snapshot_sync()

        elapsed_ms = int((time.monotonic() - self._probe_started_at) * 1000)

        try:
            self._profile.setUrlRequestInterceptor(None)
        except Exception:
            pass
        try:
            self._page.deleteLater()
        except Exception:
            pass

        return self._best_result(elapsed_ms)

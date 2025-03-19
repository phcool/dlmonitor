/*
Javascript for Deep Community.
*/

INIT_KEYWORDS = "arxiv:large language model,nature:machine learning,github:llm";

dlmonitor = {
    ajaxCount: 0,
    previewTimeout: null,
    currentPlatform: 'arxiv',  // Default platform
    sortPreferences: {}  // 存储每个列的排序偏好
};

dlmonitor.getKeywords = function() {
    var keywords = Cookies.get('keywords');
    if (Cookies.get('keywords') == undefined) {
        keywords = INIT_KEYWORDS;
    }
    if (!keywords) {
        var kwList = [];
    } else {
        var kwList = keywords.split(",");
    }
    return kwList;
};

// 添加平台特定的关键字
dlmonitor.addPlatformKeyword = function(platform) {
    var keyword = $("#new-keyword").val().trim();
    if (!keyword) {
        alert("请输入关键字");
        return;
    }
    
    dlmonitor.addKeyword(platform + ":" + keyword);
    $("#new-keyword").val("");
}

// Add platform selection function
dlmonitor.selectPlatform = function(platform) {
    dlmonitor.currentPlatform = platform;
    $("#platform-select").text(platform.charAt(0).toUpperCase() + platform.slice(1));
};

// Update addKeyword function to use current platform
dlmonitor.addKeyword = function(w) {
    if (w == undefined || typeof(w) == "object" || !w) {
        w = $("#new-keyword").val()
    }
    if (w.length == 0) {
        return;
    }
    if (w.includes(",")) {
        alert("Keyword cannot include comma.");
        return;
    }
    if (w.length > 80) {
        alert("Keyword cannot be longer than 80 characters.")
        return;
    }
    
    // 检查是否已经包含平台前缀
    if (!w.includes(":")) {
        // 如果没有前缀，添加当前平台前缀
        w = dlmonitor.currentPlatform + ":" + w;
    }
    
    $("#new-keyword").val("")
    var kwList = dlmonitor.getKeywords();
    if (kwList.length > 10) {
        alert("No more than 10 keywords, please.");
        return;
    }
    kwList.push(w.trim());
    var newKeywords = kwList.join(",");
    Cookies.set("keywords", newKeywords);
    dlmonitor.switchPreview(false);
    dlmonitor.updateAll();
};

dlmonitor.moveKeyword = function(e, dir) {
    var kwList = dlmonitor.getKeywords();
    var pos = $(e).data('pos');
    if ((pos == 0 && dir < 0) || (pos >= kwList.length - 1 && dir > 0)) {
        return;
    }
    var swapIdx = pos + dir;
    var swap = kwList[swapIdx];
    kwList[swapIdx] = kwList[pos];
    kwList[pos] = swap;
    console.log(pos,dir);
    var newKeywords = kwList.join(",");
    Cookies.set("keywords", newKeywords);
    dlmonitor.updateAll();
};

dlmonitor.removeKeyword = function(e) {
    var w = $(e).data('keyword');
    if (w == undefined) {
        return;
    }
    var kwList = dlmonitor.getKeywords();
    var index = kwList.indexOf(w);
    if (index > -1) {
        kwList.splice(index, 1);
    }
    var newKeywords = kwList.join(",");
    Cookies.set("keywords", newKeywords);
    dlmonitor.showKeywords();
    dlmonitor.updateAll();
};

// Deprecated
dlmonitor.showKeywords = function() {
    var newHtml = "";
    var kwList = dlmonitor.getKeywords();
    kwList.forEach(function(kw){
        newHtml += '<span class="label label-success" onclick="dlmonitor.removeKeyword(this);">' + kw + '</span>';
    });
    $("#keywords").html(newHtml);
};

// 从cookie加载排序偏好
dlmonitor.loadSortPreferences = function() {
    var sortPrefs = Cookies.get('sortPreferences');
    if (sortPrefs) {
        try {
            dlmonitor.sortPreferences = JSON.parse(sortPrefs);
        } catch (e) {
            console.error("Failed to parse sort preferences", e);
            dlmonitor.sortPreferences = {};
        }
    }
};

// 保存排序偏好到cookie
dlmonitor.saveSortPreferences = function() {
    Cookies.set('sortPreferences', JSON.stringify(dlmonitor.sortPreferences));
};

// 获取特定keyword的排序偏好
dlmonitor.getSortPreference = function(keyword) {
    return dlmonitor.sortPreferences[keyword] || 'time';
};

// 设置排序和刷新数据
dlmonitor.sortColumn = function(index, sortType) {
    var kw = $("#column-title-" + index).text();
    
    // 更新排序偏好
    dlmonitor.sortPreferences[kw] = sortType;
    dlmonitor.saveSortPreferences();
    
    // 更新UI，添加适当的图标
    var iconHtml = '';
    if (sortType === 'time') {
        iconHtml = '<i class="fas fa-clock"></i> ';
    } else if (sortType === 'relevance') {
        iconHtml = '<i class="fas fa-search"></i> ';
    } else if (sortType === 'popularity') {
        iconHtml = '<i class="fas fa-fire"></i> ';
    }
    
    $("#sort-info-" + index).html(iconHtml + sortType.charAt(0).toUpperCase() + sortType.slice(1));
    
    // 重新加载数据
    var parts = kw.split(":");
    if (parts.length === 2) {
        var src = parts[0];
        dlmonitor.fetch(src, kw, index, 0, sortType);
    }
};

dlmonitor.fetch = function(src_name, keyword, index, start, sortType) {
    if (start == undefined) start = 0;
    if (sortType == undefined) sortType = dlmonitor.getSortPreference(keyword);
    
    console.log("fetch", src_name, keyword, index, start, sortType);
    $("#posts-" + index).html(
        "<div style='text-align:center;'>"+
        "<img src='https://cdnjs.cloudflare.com/ajax/libs/semantic-ui/0.16.1/images/loader-large.gif'/>"+
        "</div>");
    dlmonitor.ajaxCount ++;
    
    // Get current date range
    var datetoken = Cookies.get('datetoken');
    if (!datetoken) {
        datetoken = '2-week';
    }
    
    $.ajax({
       url: '/fetch',
       type: 'POST',
       data: {
          src: src_name,
          start: "" + start,
          keyword: keyword,
          datetoken: datetoken,
          sort: sortType  // 添加排序参数
       },
       error: function() {
           dlmonitor.ajaxCount --;
           alert("Error when fetching data.");
       },
       success: function(data) {
          // console.log(data);
          dlmonitor.ajaxCount --;
          $("#posts-" + index).html(data);
       }
    });
};

dlmonitor.convertDateInfo = function(token) {
    var dateinfo = "Recent two weeks";
    switch (token) {
        case '1-week':
            dateinfo = "Recent one week";
            break;
        case '2-week':
            dateinfo = "Recent two weeks";
            break;
        case '1-month':
            dateinfo = "Recent one month";
            break;
    }
    return dateinfo;
};

dlmonitor.showDate = function() {
    var datetoken = Cookies.get('datetoken');
    if (!datetoken) {
        datetoken = '2-week';
    }
    $("#date-info").html(dlmonitor.convertDateInfo(datetoken));
};

dlmonitor.filterDate = function(token) {
    Cookies.set('datetoken', token);
    dlmonitor.updateAll();
};

dlmonitor.placeColumns = function() {
    var kwList = dlmonitor.getKeywords();
    var currentNum = $(".post-columns .column").length
    // Create columns
    if (kwList.length != currentNum) {
        var newHtml = "";
        for (var i = 0; i < kwList.length; ++i) {
            var template = $("#column-template").html()
            for (var j = 0; j < 6; ++j) {
                template = template.replace("NUM", "" + i);
            }
            newHtml += template;
        }
        $("#post-columns").html(newHtml);
    }
    // Fill titles
    for (var i = 0; i < kwList.length; ++i) {
        $("#column-title-" + i).html(kwList[i]);
        $("#close-btn-" + i).data("keyword", kwList[i])
        $("#left-btn-" + i).data("pos", i)
        $("#right-btn-" + i).data("pos", i)
    }
};

// Deprecated
dlmonitor.fixFloat = function() {
    if (dlmonitor.ajaxCount != 0) return;
    var threshold = $("#post-columns").position().left + 1200 / 2;
    $(".post-columns .column").each(function(i, e) {
        if ($(e).position().left > threshold) {
            $(e).css("float", "right");
        }
    });
};

// Update updateAll function to handle platform:query format
dlmonitor.updateAll = function(nofetch) {
    dlmonitor.showDate();
    dlmonitor.placeColumns();
    if (nofetch == true) return;
    var kwList = dlmonitor.getKeywords();
    for (var i = 0; i < kwList.length; ++i) {
        var parts = kwList[i].split(":");
        if (parts.length === 2) {
            var src = parts[0];
            var keyword = parts[1];
            dlmonitor.fetch(src, kwList[i], i, 0);
        }
    }
};

dlmonitor.switchPreview = function(flag) {
    if (flag) {
        $(".preview").show();
        $(".post-columns").hide();
    } else {
        $(".preview").hide();
        $(".post-columns").show();
    }
};

dlmonitor.load_fulltext = function(arxiv_token) {
  dlmonitor.ajaxCount ++;
  $.ajax({
     url: '/load_fulltext/' + arxiv_token,
     type: 'GET',
     error: function() {
          dlmonitor.ajaxCount --;
          $("#latex-content").html("An error is detected when loading the paper.");
     },
     success: function(data) {
        // console.log(data);
        dlmonitor.ajaxCount --;
        $("#latex-content").data("arxiv_token", arxiv_token);
        setTimeout(dlmonitor.retrieve_fulltext, 3000);
     }
  });
}

dlmonitor.retrieve_fulltext = function() {
  dlmonitor.ajaxCount ++;
  arxiv_token = $("#latex-content").data("arxiv_token")
  $.ajax({
     url: '/retrieve_fulltext/' + arxiv_token,
     type: 'GET',
     error: function() {
          dlmonitor.ajaxCount --;
          $("#latex-content").html("An error is detected when loading the paper.");
     },
     success: function(data) {
        // console.log(data);
        dlmonitor.ajaxCount --;
        if (data == "PROCESSING" || data == "NOT_EXIST") {
          setTimeout(dlmonitor.retrieve_fulltext, 3000);
        } else if (data == "NOT_AVAILABE") {
          $("#latex-content").html("This feature is not avaialbe for this paper.");
        } else {
          $("#latex-content").html(data);
        }
     }
  });
};

// Update preview functionality to use current platform
dlmonitor.init = function() {
    // 加载排序偏好
    dlmonitor.loadSortPreferences();
    
    dlmonitor.updateAll(true);
    $("#new-keyword").keypress(function(e) {
        if(e.which == 13) {
            dlmonitor.addKeyword();
            return false;
        }
    });
    $("#new-keyword-btn").click(function(){
        dlmonitor.addKeyword();
    });
    $('#new-keyword').on('keyup', function() {
        clearTimeout(dlmonitor.previewTimeout);
        dlmonitor.previewTimeout = setTimeout(function() {
            var text = $("#new-keyword").val();
            if ($("#new-keyword").is(":focus") && text.length >= 3) {
                $("#preview-kw").html(dlmonitor.currentPlatform + ":" + text);
                $("#posts-preview").height(($(window).height() - 160) + "px")
                dlmonitor.switchPreview(true);
                dlmonitor.fetch(dlmonitor.currentPlatform, dlmonitor.currentPlatform + ":" + text, 'preview');
            } else {
                dlmonitor.switchPreview(false);
            }
        }, 200);
        if ($("#new-keyword").val().length < 3) {
            dlmonitor.switchPreview(false);
        }
    });
    $("#close-btn-preview").on('click tap', function() {
            dlmonitor.switchPreview(false);
            $("#new-keyword").val('');
    });
};

// Document ready
$(function(){
    dlmonitor.updateAll();
    $("#new-keyword").keypress(function(e) {
        // Enter key pressed
        if(e.which == 13) {
            dlmonitor.addKeyword();
            return false;
        }
    });
    $("#new-keyword-btn").click(function(){
        dlmonitor.addKeyword();
    });
});

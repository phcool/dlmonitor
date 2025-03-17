/*
Javascript for Deep Community.
*/

INIT_KEYWORDS = "arxiv:reinforcement learning,twitter:machine learning,arxiv:language,twitter:AI news";

dlmonitor = {
    ajaxCount: 0,
    previewTimeout: null,
    currentPlatform: 'arxiv' // 默认平台为arxiv
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

// 设置当前选择的平台
dlmonitor.setPlatform = function(platform) {
    dlmonitor.currentPlatform = platform;
    $("#platform-selection").text(platform.charAt(0).toUpperCase() + platform.slice(1));
}

// 添加平台特定的关键字 - 不再需要，由setPlatform和addKeyword共同完成
dlmonitor.addPlatformKeyword = function(platform) {
    var keyword = $("#new-keyword").val().trim();
    if (!keyword) {
        alert("Please enter keywords");
        return;
    }
    
    dlmonitor.addKeyword(platform + ":" + keyword);
    $("#new-keyword").val("");
}

// This requires js-cookie
dlmonitor.addKeyword = function(w) {
    if (w == undefined || typeof(w) == "object" || !w) {
        w = $("#new-keyword").val()
    }
    if (w.length == 0) {
        return;
    }
    if (w.includes(",")) {
        alert("Keyword can not include comma.");
        return;
    }
    if (w.length > 80) {
        alert("Keyword can not longer than 80 chars.")
        return;
    }
    // 确保关键字符合平台:查询格式
    if (!w.includes(":")) {
        // 使用当前选择的平台
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
    // dlmonitor.showKeywords();
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

dlmonitor.fetch = function(src_name, keyword, index, start) {
    if (start == undefined) start = 0;
    console.log("fetch", src_name, keyword, index, start);
    $("#posts-" + index).html(
        "<div style='text-align:center;'>"+
        "<img src='https://cdnjs.cloudflare.com/ajax/libs/semantic-ui/0.16.1/images/loader-large.gif'/>"+
        "</div>");
    dlmonitor.ajaxCount ++;
    $.ajax({
       url: '/fetch',
       type: 'POST',
       data: {
          src: src_name,
          start: "" + start,
          keyword: keyword
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

dlmonitor.updateAll = function(nofetch) {
    dlmonitor.showDate();
    dlmonitor.placeColumns();
    if (nofetch == true) return;
    var kwList = dlmonitor.getKeywords();
    for (var i = 0; i < kwList.length; ++i) {
        var src;
        if (kwList[i].includes(":")) {
            // 新格式 platform:query
            src = kwList[i].split(":")[0].trim().toLowerCase();
        } else if (kwList[i].toLowerCase().includes("tweets")) {
            // 兼容旧格式
            src = 'twitter';
        } else {
            // 默认
            src = 'arxiv';
        }
        dlmonitor.fetch(src, kwList[i], i, start=0);
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

dlmonitor.save_mendeley = function(pdf_url, paper_title) {
    $.notify("Saving " + paper_title, "info");
    dlmonitor.ajaxCount ++;
    $.ajax({
       url: '/save_mendeley',
       type: 'GET',
       data: {
          url: pdf_url
       },
       error: function() {
            dlmonitor.ajaxCount --;
            $.notify("Error when saving paper.", "error");
       },
       success: function(data) {
          // console.log(data);
          dlmonitor.ajaxCount --;
          $.notify(data, "success");
       }
    });
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

dlmonitor.init = function() {
    dlmonitor.updateAll(true);
    // 设置默认平台
    dlmonitor.setPlatform('arxiv');
    
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
    $('#new-keyword').on('keyup', function() {
        clearTimeout(dlmonitor.previewTimeout);
        dlmonitor.previewTimeout = setTimeout(function() {
            var text = $("#new-keyword").val();
            if ($("#new-keyword").is(":focus") && text.length >= 3) {
                $("#preview-kw").html(text);
                $("#posts-preview").height(($(window).height() - 160) + "px")
                dlmonitor.switchPreview(true);
                // 使用当前平台进行预览
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
    dlmonitor.init();
});

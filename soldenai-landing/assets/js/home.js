
  document.documentElement.classList.remove('no-js');
  document.documentElement.classList.add('js');
  (function(){
    var motionOK = !window.matchMedia || window.matchMedia('(prefers-reduced-motion: no-preference)').matches;
    if(!motionOK){document.querySelectorAll('.reveal').forEach(function(e){e.classList.add('in');});return;}
    var els=[].slice.call(document.querySelectorAll('.reveal'));
    function check(){var vh=window.innerHeight||document.documentElement.clientHeight;for(var i=els.length-1;i>=0;i--){var e=els[i];var r=e.getBoundingClientRect();if(r.top<vh*0.92&&r.bottom>0){e.classList.add('in');els.splice(i,1);}}}
    var t=false;function onS(){if(!t){t=true;requestAnimationFrame(function(){check();t=false;});}}
    window.addEventListener('scroll',onS,{passive:true});window.addEventListener('resize',onS);
    check();requestAnimationFrame(check);setTimeout(check,160);
    if('IntersectionObserver' in window){var io=new IntersectionObserver(function(en){en.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}});},{threshold:0.08,rootMargin:'0px 0px -6% 0px'});els.forEach(function(e){io.observe(e);});}
    setTimeout(function(){document.querySelectorAll('.reveal').forEach(function(e){e.classList.add('in');});},3800);
  })();

  // How-it-works: cycle the same record across surfaces (ERP -> Slack -> Email -> Agent)
  (function(){
    var surf=document.querySelector('.surf');
    if(!surf)return;
    var tabs=[].slice.call(surf.querySelectorAll('.surf-tools span'));
    var views=[].slice.call(surf.querySelectorAll('.surf-view'));
    if(!tabs.length||!views.length)return;
    var motionOK = !window.matchMedia || window.matchMedia('(prefers-reduced-motion: no-preference)').matches;
    var cur=0, timer=null;
    function show(i){
      cur=i;
      tabs.forEach(function(t,n){t.classList.toggle('on',n===i);});
      views.forEach(function(v,n){v.classList.toggle('on',n===i);});
    }
    function next(){show((cur+1)%views.length);}
    function start(){if(motionOK&&!timer)timer=setInterval(next,2600);}
    function stop(){if(timer){clearInterval(timer);timer=null;}}
    tabs.forEach(function(t,n){t.style.cursor='pointer';t.addEventListener('click',function(){stop();show(n);});});
    surf.addEventListener('mouseenter',stop);
    surf.addEventListener('mouseleave',start);
    if('IntersectionObserver' in window){
      var io=new IntersectionObserver(function(en){en.forEach(function(e){if(e.isIntersecting){start();}else{stop();}});},{threshold:0.3});
      io.observe(surf);
    }
    setTimeout(start,800);
  })();

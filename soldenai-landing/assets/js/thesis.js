
  document.documentElement.classList.remove('no-js');
  (function(){
    var prog=document.getElementById('prog');
    function upd(){var h=document.documentElement.scrollHeight-window.innerHeight;var p=h>0?(window.scrollY/h):0;prog.style.width=(p*100)+'%';}
    window.addEventListener('scroll',upd,{passive:true});window.addEventListener('resize',upd);upd();
  })();

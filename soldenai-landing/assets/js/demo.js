
  document.documentElement.classList.remove('no-js');
  document.documentElement.classList.add('js');
  (function(){
    var form=document.getElementById('demoForm');
    var done=document.getElementById('doneState');
    var msg=document.getElementById('doneMsg');
    if(!form)return;
    var btn=form.querySelector('.submit');
    var errEl=null;
    function showError(text){
      if(!errEl){
        errEl=document.createElement('p');
        errEl.className='finehint';
        errEl.style.color='#9A2A2A';
        btn.insertAdjacentElement('afterend',errEl);
      }
      errEl.textContent=text;
    }
    function val(id){var el=document.getElementById(id);return el?(el.value||'').trim():'';}
    form.addEventListener('submit',function(e){
      e.preventDefault();
      if(!form.checkValidity()){form.reportValidity();return;}
      var fn=val('fname'), ln=val('lname'), email=val('email');
      var team=val('team'), ctx=val('ctx');
      var parts=[];
      if(team)parts.push('Team size: '+team);
      if(ctx)parts.push('Workflow to hold: '+ctx);
      var payload={
        name:(fn+' '+ln).trim(),
        email:email,
        company:val('company'),
        role:val('role'),
        topic:'demo',
        message:parts.join('\n\n'),
        company_website:val('company_website')
      };
      if(errEl)errEl.textContent='';
      var label=btn.innerHTML; btn.disabled=true; btn.textContent='Sending…';
      fetch('/api/contact',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)})
        .then(function(r){return r.json().catch(function(){return {ok:r.ok};});})
        .then(function(d){
          if(d&&d.ok){
            msg.textContent='Thanks'+(fn?(', '+fn):'')+'. We’ll reach out at '+email+' to set up your walkthrough, and a confirmation is on its way to your inbox now.';
            form.style.display='none';
            done.classList.add('show');
            done.scrollIntoView({block:'nearest'});
          }else{
            btn.disabled=false; btn.innerHTML=label;
            showError('Something went wrong sending that. Please try again, or email hello@soldenai.com.');
          }
        })
        .catch(function(){
          btn.disabled=false; btn.innerHTML=label;
          showError('Network error. Please try again, or email hello@soldenai.com.');
        });
    });
  })();

